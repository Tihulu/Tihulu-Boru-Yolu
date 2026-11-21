"""Boru Core agent scheduler: logical agents, DAG dependencies, resource leases.

Six *logical* agents are scheduling roles, not six concurrently loaded models.
The default physical lease is one large local model at a time until real RAM
and VRAM measurements exist; leases are counted, never guessed from a device
inventory.  Cleanup only ever releases Boru-owned leases: nothing here can
stop, unload or reconfigure an external Jan or OpenCode session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import PolicyViolation
from .policy import Policy
from .state import TaskState
from .types import TaskEnvelope

MAX_LOGICAL_AGENTS = 6
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
    """Counts Boru-owned resource leases.  It never inspects a host device."""

    large_local_models: int = 0
    remote_calls: int = 0
    agents_active: int = 0
    _owners: Dict[str, Set[str]] = field(default_factory=dict)

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

    def acquire(self, kind: str, owner: str) -> None:
        self._add(kind, owner, 1)

    def release(self, kind: str, owner: str) -> None:
        self._add(kind, owner, -1)

    def holds(self, kind: str, owner: str) -> bool:
        return owner in self._owners.get(kind, set())


class AgentScheduler:
    """Bounded DAG scheduler over Boru-owned logical agents."""

    def __init__(self, policy: Policy, *, max_agents: Optional[int] = None, max_large_local_models: int = 1) -> None:
        if isinstance(max_large_local_models, bool) or not isinstance(max_large_local_models, int) or not 0 <= max_large_local_models <= 2:
            raise PolicyViolation("max_large_local_models must be 0..2 until measured")
        limit = max_agents if max_agents is not None else policy.max_agents
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LOGICAL_AGENTS:
            raise PolicyViolation("max_agents must be 1..6 logical agents")
        self.policy = policy
        self.max_agents = limit
        self.max_large_local_models = max_large_local_models
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

    def release(self, task_id: str) -> None:
        """Release only Boru-owned leases for one task (idempotent)."""
        self.leases.release("agents_active", task_id)
        self.leases.release("large_local_models", task_id)

    def release_all(self) -> None:
        for task_id in self._order:
            self.release(task_id)
        self.leases.remote_calls = 0


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
