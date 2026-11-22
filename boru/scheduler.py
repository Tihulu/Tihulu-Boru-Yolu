"""Boru Core agent scheduler: logical agents, DAG dependencies, resource leases.

Six *logical* agents are scheduling roles, not six concurrently loaded models.
Leases are counted, never guessed from a device inventory, and the profile
(`boru.resources`) sets how long a kept-warm model lease may sit idle before
Boru releases it.  Cleanup only ever releases Boru-owned leases: nothing here
can stop, unload or reconfigure an external Jan or OpenCode session — releasing
the *model* is a provider decision (`ChatProvider.unload`).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import PolicyViolation
from .policy import Policy
from .resources import MAX_AGENTS, MAX_LARGE_LOCAL_MODELS, ResourceMode, ResourceProfile
from .state import TaskState
from .types import TaskEnvelope

MAX_PLAN_TASKS = 64


@dataclass(frozen=True)
class AgentSpec:
    """One logical agent role in a plan."""

    agent_id: str
    task_id: str
    capability_tags: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()
    large_local_model: bool = False

    def validate(self, max_agents: int) -> List[str]:
        errors: List[str] = []
        for name in ("agent_id", "task_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                errors.append(name + " must be a bounded non-empty string")
        if not isinstance(self.capability_tags, tuple) or any(
            not isinstance(i, str) or not i.strip() or len(i) > 64 for i in self.capability_tags
        ):
            errors.append("capability_tags must be a tuple of bounded non-empty strings")
        if not isinstance(self.depends_on, tuple) or any(
            not isinstance(i, str) or not i.strip() or len(i) > 128 for i in self.depends_on
        ):
            errors.append("depends_on must be a tuple of bounded task IDs")
        if self.task_id in self.depends_on:
            errors.append("a task cannot depend on itself")
        if not isinstance(self.large_local_model, bool):
            errors.append("large_local_model must be a boolean")
        return errors


@dataclass
class LeaseLedger:
    """Counts Boru-owned resource leases.  It never inspects a host device.

    Each lease records when it was last used, so a kept-warm model lease can be
    released after an idle period instead of being held forever.
    """

    large_local_models: int = 0
    remote_calls: int = 0
    agents_active: int = 0
    _owners: Dict[str, Set[str]] = field(default_factory=dict)
    _last_used: Dict[Tuple[str, str], float] = field(default_factory=dict)

    def _add(self, kind: str, owner: str, amount: int) -> None:
        current = set(self._owners.setdefault(kind, set()))
        if amount > 0:
            current.add(owner)
        else:
            current.discard(owner)
        self._owners[kind] = current
        if kind == "large_local_models":
            self.large_local_models = len(current)
        elif kind == "remote_calls":
            self.remote_calls = max(self.remote_calls - amount, 0) if amount < 0 else self.remote_calls + amount
        elif kind == "agents_active":
            self.agents_active = len(current)

    def acquire(self, kind: str, owner: str, now: Optional[float] = None) -> None:
        self._add(kind, owner, 1)
        self._last_used[(kind, owner)] = time.time() if now is None else float(now)

    def release(self, kind: str, owner: str) -> None:
        self._add(kind, owner, -1)
        self._last_used.pop((kind, owner), None)

    def touch(self, kind: str, owner: str, now: Optional[float] = None) -> None:
        """Record a use of a held lease (an in-flight task is never idle)."""
        if owner in self._owners.get(kind, set()):
            self._last_used[(kind, owner)] = time.time() if now is None else float(now)

    def idle_seconds(self, kind: str, owner: str, now: Optional[float] = None) -> Optional[float]:
        stamp = self._last_used.get((kind, owner))
        if stamp is None:
            return None
        return (time.time() if now is None else float(now)) - stamp

    def holds(self, kind: str, owner: str) -> bool:
        return owner in self._owners.get(kind, set())

    def owners(self, kind: str) -> Tuple[str, ...]:
        return tuple(sorted(self._owners.get(kind, set())))


class AgentScheduler:
    """Bounded DAG scheduler over Boru-owned logical agents."""

    def __init__(self, policy: Policy, *, max_agents: Optional[int] = None, max_large_local_models: Optional[int] = None,
                 profile: Optional[ResourceProfile] = None) -> None:
        if profile is not None:
            profile.assert_valid()
        self.profile = profile if profile is not None else ResourceProfile(mode=ResourceMode.BALANCED)
        # An explicit caller value is a hard request: it must already fit the
        # policy ceiling.  A profile-derived value is clamped to that ceiling,
        # so a resource profile can widen performance but never policy.
        requested = max_agents if max_agents is not None else self.profile.max_agents
        if isinstance(requested, bool) or not isinstance(requested, int) or not 1 <= requested <= MAX_AGENTS:
            raise PolicyViolation("max_agents must be 1..{} logical agents".format(MAX_AGENTS))
        if requested > policy.max_agents:
            if max_agents is not None:
                raise PolicyViolation("max_agents exceeds the policy ceiling")
            requested = policy.max_agents
        models = max_large_local_models if max_large_local_models is not None \
            else self.profile.max_large_local_models
        if isinstance(models, bool) or not isinstance(models, int) or not 0 <= models <= MAX_LARGE_LOCAL_MODELS:
            raise PolicyViolation("max_large_local_models must be 0..{}".format(MAX_LARGE_LOCAL_MODELS))
        self.policy = policy
        self.max_agents = requested
        self.max_large_local_models = models
        self.leases = LeaseLedger()
        self._specs: Dict[str, AgentSpec] = {}
        self._order: List[str] = []

    # -- plan intake ---------------------------------------------------------
    def add(self, spec: AgentSpec) -> AgentSpec:
        errors = spec.validate(self.max_agents)
        if errors:
            raise PolicyViolation("; ".join(errors))
        if len(self._specs) >= MAX_PLAN_TASKS:
            raise PolicyViolation("plan exceeds the bounded task count")
        if spec.task_id in self._specs:
            raise PolicyViolation("duplicate task id in plan")
        for dependency in spec.depends_on:
            if dependency not in self._specs:
                raise PolicyViolation("unknown dependency: " + str(dependency))
        self._specs[spec.task_id] = spec
        self._order.append(spec.task_id)
        return spec

    def add_many(self, specs: Iterable[AgentSpec]) -> None:
        for spec in specs:
            self.add(spec)

    # -- queries -------------------------------------------------------------
    def tasks(self) -> List[str]:
        return list(self._order)

    def spec(self, task_id: str) -> AgentSpec:
        if task_id not in self._specs:
            raise PolicyViolation("unknown task id")
        return self._specs[task_id]

    def dependents(self, task_id: str) -> List[str]:
        return [tid for tid in self._order if task_id in self._specs[tid].depends_on]

    def ready(self, states: Dict[str, TaskState]) -> List[str]:
        """Return task IDs whose dependencies are all DONE, preserving plan order."""
        ready: List[str] = []
        for task_id in self._order:
            if states.get(task_id) is TaskState.DONE:
                continue
            if all(states.get(dep) is TaskState.DONE for dep in self._specs[task_id].depends_on):
                ready.append(task_id)
        return ready

    def blocked(self, states: Dict[str, TaskState]) -> List[str]:
        """Pending tasks whose dependencies are not yet DONE."""
        ready = set(self.ready(states))
        return [tid for tid in self._order if tid not in ready and states.get(tid) is not TaskState.DONE]

    # -- leases --------------------------------------------------------------
    def can_lease(self, spec: AgentSpec) -> Tuple[bool, str]:
        if self.leases.agents_active >= self.max_agents:
            return False, "logical_agent_limit"
        if spec.large_local_model and self.leases.large_local_models >= self.max_large_local_models:
            return False, "large_local_model_limit"
        return True, ""

    def acquire(self, spec: AgentSpec) -> None:
        allowed, reason = self.can_lease(spec)
        if not allowed:
            raise PolicyViolation("lease refused: " + reason)
        self.leases.acquire("agents_active", spec.task_id)
        if spec.large_local_model:
            self.leases.acquire("large_local_models", spec.task_id)

    def release(self, task_id: str, *, keep_model: bool = False) -> None:
        """Release the agent lease for one task, and the model lease unless kept.

        ``keep_model`` is how a resource profile keeps a large local model
        open after the task that used it: the agent is finished, the model
        stays leased until it goes idle past the profile's threshold.
        """
        self.leases.release("agents_active", task_id)
        if self.leases.holds("large_local_models", task_id) and not keep_model:
            self.leases.release("large_local_models", task_id)

    def release_all(self) -> None:
        for task_id in self._order:
            self.release(task_id)
        self.leases.remote_calls = 0

    def idle_model_leases(self, now: Optional[float] = None) -> List[str]:
        """Owners whose held model lease sat idle past the profile threshold."""
        if not self.profile.evicts_idle():
            return []
        evictable = []
        for owner in self.leases.owners("large_local_models"):
            idle = self.leases.idle_seconds("large_local_models", owner, now)
            if idle is not None and idle >= self.profile.idle_eviction_seconds:
                evictable.append(owner)
        return evictable

    def evict_idle(self, now: Optional[float] = None) -> List[str]:
        """Release Boru-owned model leases that went idle past the threshold."""
        evicted = self.idle_model_leases(now)
        for owner in evicted:
            self.leases.release("large_local_models", owner)
        return evicted


def build_envelopes(specs: Sequence[AgentSpec], goal: str, parent: Optional[str] = None) -> List[TaskEnvelope]:
    """Turn agent specs into task envelopes that inherit the parent's axes."""
    envelopes: List[TaskEnvelope] = []
    for spec in specs:
        envelopes.append(
            TaskEnvelope(
                task_id=spec.task_id,
                goal=goal,
                capability_tags=spec.capability_tags,
                parent_task_id=parent,
                max_parallel=1,
                deadline=None,
            )
        )
    return envelopes
