"""Boru Core: scheduling, dispatch, verification and durable task state.

Design constraints enforced here rather than in prompts:

* The four policy axes are read from one immutable ``Policy``; no model
  reply, routing preset or provider switch can widen them.
* A completed reply only reaches ``REVIEW``.  ``DONE`` requires an explicit
  owner review recorded in the local task history, and the evidence class is
  preserved so a simulated result is never relabelled as live.
* ``MANUAL`` routing needs an owner-selected provider/model; otherwise the
  task is held, never silently substituted.
* P1 supports text-only local providers.  A cloud request under ``CLOUD_ALLOWED``
  is held as ``unsupported_inference`` because no cloud provider is configured
  or verified in this slice.
* Budget ceilings are held *before* dispatch when usage cannot be reserved:
  Boru Core never issues a call it cannot account for.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import CoreConfig
from .errors import ContractError, PolicyViolation, StoreError, VerificationError
from .policy import LOCAL_PROVIDERS
from .providers.base import ChatMessage, ChatReply, ProviderFailure
from .audit import RejectionLedger
from .boundary import CrossBoundaryGuard
from .budgets import Budget, BudgetLedger, CooldownTracker, compact, estimate_message_tokens
from .router import Router, RoutingDecision, should_retry
from .scheduler import AgentScheduler, AgentSpec, build_envelopes
from .state import TaskState, can_transition, utc_now
from .store import TaskStore
from .types import SCHEMA_VERSION, AgentResult, TaskEnvelope

CAPABILITIES = ("text",)

#: Stable audit reasons. Provider text is never used as a reason category.
REASONS = {
    "CREATED": "submitted",
    "CLASSIFIED": "classified",
    "PLANNED": "planned",
    "QUEUED": "queued",
    "RUNNING": "dispatch_started",
    "VERIFYING": "reply_recorded",
    "REVIEW": "reply_recorded",
    "DONE": "owner_review_done",
    "FAILED": "owner_review_failed",
    "CANCELLED": "cancelled",
    "unsupported_capability": "unsupported_capability",
    "unsupported_inference": "unsupported_inference",
    "manual_selection_required": "manual_selection_required",
    "provider_unavailable": "provider_unavailable",
    "invalid_reply": "invalid_reply",
    "budget_unverifiable": "budget_unverifiable",
    "budget_exceeded_pre": "budget_exceeded_pre_dispatch",
    "cost_ceiling_unresolved": "cost_ceiling_unresolvable_before_dispatch",
    "unclassified_boundary": "unclassified_boundary",
    "budget_exceeded_post": "budget_exceeded_after_reported_usage",
    "context_compacted": "context_compacted",
    "deadline_exceeded": "deadline_exceeded",
    "verification_failed": "verification_failed",
    "interrupted": "interrupted",
    "missing_provider": "missing_provider",
}


def _registry_for(config: CoreConfig, providers: Dict[str, Any]):
    """Build a registry from the configured providers and their allowlists."""
    from .registry import ModelRecord, ModelRegistry

    registry = ModelRegistry()
    for entry in config.providers:
        if entry.kind == "jan":
            for model_id in entry.local_model_ids:
                registry.register(ModelRecord(provider="jan", model_id=model_id, source="configured",
                                              health="unknown", tags=("text",), local=True))
        elif entry.kind == "mock":
            from .providers.mock import MODEL_ID

            registry.register(ModelRecord(provider="mock", model_id=MODEL_ID, source="verified",
                                          health="healthy", tags=("text",), local=True))
        elif entry.kind == "cloud":
            provider_name = entry.api_key_env or "cloud"
            for model_id in entry.local_model_ids:
                registry.register(ModelRecord(provider=provider_name, model_id=model_id, source="configured",
                                              health="unknown", tags=("text",), local=False))
    return registry


class BoruCore:
    """Local-first orchestrator with durable, reviewable task state."""

    def __init__(self, config: CoreConfig, store: Optional[TaskStore] = None, clock=None, registry=None,
                 audit: Optional[RejectionLedger] = None) -> None:
        config.assert_valid()
        self.config = config
        self.policy = config.policy
        self.store = store if store is not None else TaskStore(max_records=config.max_records)
        self._clock = clock or utc_now
        self._cloud_states: Dict[str, str] = {}
        self._providers = self._build_providers(config)
        self.audit = audit if audit is not None else RejectionLedger()
        self.guard = CrossBoundaryGuard()
        for spec in self.config.classifications:
            self.guard.declare(spec.task_id or "*", spec.to_classification())
        self._queue: Dict[str, TaskEnvelope] = {}
        self._last_bound_input: Dict[str, int] = {}
        self.budgets = BudgetLedger(ceiling=Budget())
        self.cooldowns = CooldownTracker(seconds=config.cooldown_seconds)
        self.router = Router(registry) if registry is not None else Router(_registry_for(config, self._providers))
        self.scheduler = AgentScheduler(config.policy, max_agents=config.policy.max_agents)
        self.budgets = BudgetLedger(ceiling=Budget())
        self.cooldowns = CooldownTracker(seconds=config.cooldown_seconds)

    # -- construction --------------------------------------------------------
    def _build_providers(self, config: CoreConfig) -> Dict[str, Any]:
        providers: Dict[str, Any] = {}
        for entry in config.providers:
            if entry.kind == "mock":
                from .providers.mock import MockProvider

                providers["mock"] = MockProvider()
            elif entry.kind == "jan":
                from .providers.jan import JanProvider

                providers["jan"] = JanProvider(
                    entry.endpoint,
                    local_model_ids=entry.local_model_ids,
                    tool_execution_disabled=entry.tool_execution_disabled,
                    allow_discovery=entry.allow_discovery,
                    model_response_is_path=entry.model_response_is_path,
                )
            elif entry.kind == "cloud":
                from .providers.cloud import CloudProvider

                name = entry.api_key_env or "cloud"
                provider = CloudProvider(
                    name.split("-")[-1],
                    entry.endpoint,
                    model_ids=entry.local_model_ids,
                    api_key_env=entry.api_key_env,
                    allow_http=entry.allow_http,
                )
                providers[name] = provider
                self._cloud_states[name] = provider.connection_state()
            else:  # pragma: no cover - config validation rejects this
                raise PolicyViolation("provider kind is not supported")
        return providers

    def provider_states(self) -> Dict[str, str]:
        """Honest per-provider connection state, never an inferred entitlement."""
        return dict(self._cloud_states)

    # -- task lifecycle ------------------------------------------------------
    def submit(self, envelope: TaskEnvelope) -> Tuple[TaskEnvelope, str]:
        """Queue one task; returns ``(envelope, state)``."""
        envelope.assert_valid()
        errors = self._task_policy_errors(envelope)
        if errors:
            self.audit.record("policy", envelope.task_id, "task_axes_refused", "policy")
            raise PolicyViolation("; ".join(errors))
        self.store.ensure_capacity()
        key = envelope.idempotency_key or envelope.task_id
        created, row = self.store.submit(
            envelope.task_id, key, envelope.to_dict(), TaskState.CREATED.value, self._clock()
        )
        if not created:
            stored_state = row["state"]
            state = TaskState(stored_state)
            if state is not TaskState.QUEUED:
                raise StoreError("task already recorded in state " + stored_state)
            self._queue[envelope.task_id] = envelope
            return envelope, state.value
        for source, target in (
            (TaskState.CREATED, TaskState.CLASSIFIED),
            (TaskState.CLASSIFIED, TaskState.PLANNED),
            (TaskState.PLANNED, TaskState.QUEUED),
        ):
            self.store.transition(
                envelope.task_id, source.value, target.value, REASONS[target.value], self._clock()
            )
        self._queue[envelope.task_id] = envelope
        return envelope, TaskState.QUEUED.value

    def _task_policy_errors(self, envelope: TaskEnvelope) -> List[str]:
        errors: List[str] = []
        axes = (envelope.inference_scope, envelope.execution_profile, envelope.disclosure_policy)
        if axes != (self.policy.inference_scope, self.policy.execution_profile, self.policy.disclosure_policy):
            errors.append("task axes must match the approved policy")
        if envelope.routing_mode != self.policy.optimization_mode:
            errors.append("routing mode must match the approved policy")
        allowed = set(CAPABILITIES)
        if set(envelope.capability_tags) - allowed:
            errors.append("P1 supports text capability only")
        if envelope.max_parallel > self.policy.max_agents:
            errors.append("max_parallel exceeds the approved agent limit")
        if envelope.consent_reference:
            errors.append("consent_reference is a reference, not an authorization")
        if self.policy.optimization_mode == "MANUAL" and not (envelope.selected_provider and envelope.selected_model):
            errors.append("MANUAL routing requires an owner-selected provider and model")
        if not self._providers_for(envelope):
            errors.append("no configured provider can serve this task")
        return errors

    def _providers_for(self, envelope: TaskEnvelope) -> List[str]:
        names = sorted(self._providers)
        if self.policy.inference_scope == "LOCAL_ONLY":
            names = [n for n in names if n in LOCAL_PROVIDERS]
        if envelope.selected_provider:
            names = [n for n in names if n == envelope.selected_provider]
        return names

    # -- plans --------------------------------------------------------------
    def submit_plan(self, specs: Sequence[AgentSpec], goal: str, parent: Optional[str] = None) -> List[str]:
        """Submit a dependency-aware plan of logical agents and return task IDs."""
        envelopes = build_envelopes(specs, goal, parent)
        for spec, envelope in zip(specs, envelopes):
            self.scheduler.add(spec)
        submitted: List[str] = []
        for spec, envelope in zip(specs, envelopes):
            try:
                self.submit(envelope)
            except StoreError:
                # The task already exists: a re-run resumes instead of failing.
                row = self.store.get(envelope.task_id)
                if row is None:  # pragma: no cover - defensive
                    raise
                if TaskState(row["state"]) is TaskState.QUEUED:
                    self._queue[envelope.task_id] = envelope
            submitted.append(envelope.task_id)
        return submitted

    def plan_states(self) -> Dict[str, TaskState]:
        states: Dict[str, TaskState] = {}
        for task_id in self.scheduler.tasks():
            row = self.store.get(task_id)
            states[task_id] = TaskState(row["state"]) if row else TaskState.CREATED
        return states

    def dispatch_ready(self) -> Optional[Dict[str, Any]]:
        """Dispatch the next plan task whose dependencies are all DONE."""
        states = self.plan_states()
        for task_id in self.scheduler.ready(states):
            return self.dispatch(task_id)
        return None

    def dispatch(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Dispatch one task by ID (dependency-independent entry point)."""
        states = self.plan_states()
        spec = self.scheduler.spec(task_id) if task_id in states else None
        if spec is not None:
            allowed, reason = self.scheduler.can_lease(spec)
            if not allowed:
                self.audit.record("scheduler", task_id, reason, "lease")
                self._hold_by_id(task_id, reason)
                return self.status(task_id)
            self.scheduler.acquire(spec)
        try:
            summary = self._dispatch_queued(task_id)
        finally:
            if spec is not None:
                self.scheduler.release(task_id)
        return summary

    def _hold_by_id(self, task_id: str, reason: str) -> None:
        row = self.store.get(task_id)
        if row is None:
            return
        state = TaskState(row["state"])
        if can_transition(state, TaskState.HOLD):
            self.store.transition(task_id, state.value, TaskState.HOLD.value, reason, self._clock())

    def _dispatch_queued(self, task_id: str) -> Optional[Dict[str, Any]]:
        for row in self.store.queued():
            if row["task_id"] != task_id:
                continue
            envelope = self._queue.get(task_id) or self._restore(task_id)
            if envelope is None:
                return None
            return self._run(envelope)
        return None

    # -- dispatch ------------------------------------------------------------
    def dispatch_next(self) -> Optional[Dict[str, Any]]:
        """Run exactly one queued task and return a bounded status summary."""
        target = self._next_queued()
        if target is None:
            return None
        envelope, state = target
        return self._run(envelope)

    def _run(self, envelope: TaskEnvelope) -> Optional[Dict[str, Any]]:
        if envelope.deadline is not None and self._deadline_passed(envelope.deadline):
            self._hold(envelope, REASONS["deadline_exceeded"])
            return self._summary(envelope)
        if envelope.cost_budget_usd is not None:
            # Cost cannot be bounded before a call without a provider price
            # table, so Boru refuses to start rather than spend unbounded money.
            self._hold(envelope, REASONS["cost_ceiling_unresolved"])
            return self._summary(envelope)
        ceiling = Budget(max_total_tokens=envelope.token_budget)
        ceiling.assert_valid()
        messages = self._messages(envelope)
        if len("".join(m.content for m in messages)) > self.config.max_context_chars:
            messages = compact(messages, max_chars=self.config.max_context_chars).messages
        estimated_input = estimate_message_tokens(messages)
        allowed, reason = self.budgets.reserve(
            envelope.task_id, estimated_input=estimated_input,
            requested_output=self.config.max_output_tokens, ceiling=ceiling)
        if not allowed:
            self._hold(envelope, REASONS["budget_exceeded_pre"])
            return self._summary(envelope)
        self._last_bound_input[envelope.task_id] = estimated_input
        previous = self.store.transition(
            envelope.task_id, TaskState.QUEUED.value, TaskState.RUNNING.value,
            REASONS["RUNNING"], self._clock(),
        )
        if previous != TaskState.QUEUED.value:
            return self._summary(envelope)
        decision = self._decide(envelope)
        if decision is None:
            self._hold(envelope, REASONS["missing_provider"])
            return self._summary(envelope)
        if not decision.ordered:
            reason = REASONS["unsupported_inference"] if self.policy.inference_scope != "LOCAL_ONLY" else REASONS["missing_provider"]
            self._hold(envelope, reason)
            return self._summary(envelope)
        attempt_id = "att-" + uuid.uuid4().hex
        remaining = [c for c in decision.ordered
                     if self.cooldowns.available(c.provider, c.model_id)] or list(decision.ordered)
        attempts = 0
        while remaining and attempts <= self.policy.max_retries:
            candidate = remaining.pop(0)
            attempts += 1
            provider = self._providers.get(candidate.provider)
            kind = self._provider_kind(candidate.provider)
            if kind in ("jan", "cloud"):
                # A real outbound transport must be declared before it is used.
                recipient = "cloud" if kind == "cloud" else "local"
                if not self._boundary_declared(envelope, recipient):
                    self.audit.record("policy", envelope.task_id, "unclassified_boundary", "policy")
                    self._hold(envelope, REASONS["unclassified_boundary"])
                    return self._summary(envelope)
            if provider is None:
                continue
            self.router.registry.mark_health(candidate.provider, candidate.model_id, "degraded", "provider_missing")
            try:
                reply = provider.chat(
                    candidate.model_id,
                    self._messages(envelope),
                    max_tokens=self.config.max_output_tokens,
                    timeout=self.config.request_timeout,
                )
            except ProviderFailure as failure:
                self.router.registry.mark_health(candidate.provider, candidate.model_id, "degraded", failure.category)
                if failure.category in ("rate_limited", "timeout", "server_error"):
                    self.cooldowns.cool(candidate.provider, candidate.model_id)
                if should_retry(failure.category) and remaining and attempts <= self.policy.max_retries:
                    continue
                if failure.category in ("timeout", "unavailable", "rate_limited", "server_error", "unauthorized"):
                    self._hold(envelope, REASONS["provider_unavailable"])
                else:
                    self._fail(envelope, REASONS["invalid_reply"])
                return self._summary(envelope)
            if attempts > 1 or True:
                self.router.registry.mark_tested(candidate.provider, candidate.model_id, self._clock())
            return self._record(envelope, attempt_id, candidate.provider, candidate.model_id, reply, ceiling)
        self._hold(envelope, REASONS["provider_unavailable"])
        return self._summary(envelope)
        result = self._result(envelope, attempt_id, provider_name, model_id, reply)
        problems = result.validate(self.policy.max_result_fields)
        if problems or not self._reply_matches(reply, provider_name, model_id):
            self.store.transition(
                envelope.task_id, TaskState.RUNNING.value, TaskState.VERIFYING.value,
                REASONS["VERIFYING"], self._clock(),
            )
            self.store.transition(
                envelope.task_id, TaskState.VERIFYING.value, TaskState.REVIEW.value,
                REASONS["VERIFYING"], self._clock(),
            )
            self.store.transition(
                envelope.task_id, TaskState.REVIEW.value, TaskState.FAILED.value,
                REASONS["verification_failed"], self._clock(),
            )
            self.store.save_result(envelope.task_id, attempt_id, result)
            return self._summary(envelope)
        self.store.save_result(envelope.task_id, attempt_id, result)
        self._queue.pop(envelope.task_id, None)
        self.store.transition(
            envelope.task_id, TaskState.RUNNING.value, TaskState.VERIFYING.value,
            REASONS["VERIFYING"], self._clock(),
        )
        self.store.transition(
            envelope.task_id, TaskState.VERIFYING.value, TaskState.REVIEW.value,
            REASONS["VERIFYING"], self._clock(),
        )
        return self._summary(envelope)

    def _provider_kind(self, provider_name: str) -> str:
        for entry in self.config.providers:
            if entry.kind == "jan" and provider_name == "jan":
                return "jan"
            if entry.kind == "cloud" and provider_name == (entry.api_key_env or "cloud"):
                return "cloud"
            if entry.kind == "mock" and provider_name == "mock":
                return "mock"
        return "unknown"

    def _boundary_declared(self, envelope: TaskEnvelope, recipient: str) -> bool:
        """An outbound direction must be declared before any call (issue #9)."""
        allowed, _ = self.guard.check(envelope.task_id, recipient=recipient, boundary="model_inference",
                                      data_class="none")
        if allowed:
            return True
        allowed, _ = self.guard.check("*", recipient=recipient, boundary="model_inference",
                                      data_class="none")
        return allowed

    def _decide(self, envelope: TaskEnvelope) -> Optional[RoutingDecision]:
        """Choose candidates without ever widening the policy axes."""
        try:
            return self.router.decide(
                mode=self.policy.optimization_mode,
                inference_scope=self.policy.inference_scope,
                complexity=envelope.complexity,
                required_tags=envelope.capability_tags,
                selected_provider=envelope.selected_provider,
                selected_model=envelope.selected_model,
                max_parallel=envelope.max_parallel,
            )
        except PolicyViolation:
            return None

    def _fail(self, envelope: TaskEnvelope, reason: str) -> None:
        self.audit.record("scheduler", envelope.task_id, reason, "failed")
        row = self.store.get(envelope.task_id)
        if row is None:
            return
        state = TaskState(row["state"])
        if can_transition(state, TaskState.FAILED):
            self.store.transition(envelope.task_id, state.value, TaskState.FAILED.value, reason, self._clock())
            self._queue.pop(envelope.task_id, None)

    def _record(self, envelope, attempt_id, provider_name, model_id, reply, ceiling) -> Dict[str, Any]:
        """Verify and store a reply; only REVIEW is reachable from here."""
        result = self._result(envelope, attempt_id, provider_name, model_id, reply)
        problems = result.validate(self.policy.max_result_fields)
        if problems or not self._reply_matches(reply, provider_name, model_id):
            self.store.save_result(envelope.task_id, attempt_id, result)
            self._fail(envelope, REASONS["verification_failed"])
            return self._summary(envelope)
        ceiling_ok, ceiling_reason = self.budgets.record(
            envelope.task_id, dict(reply.usage), None)
        if not ceiling_ok and (ceiling.max_total_tokens or ceiling.max_cost_usd):
            self._hold(envelope, REASONS["budget_exceeded_post"])
            return self._summary(envelope)
        self.store.save_result(envelope.task_id, attempt_id, result)
        self._queue.pop(envelope.task_id, None)
        source = TaskState.RUNNING.value
        for target in (TaskState.VERIFYING.value, TaskState.REVIEW.value):
            self.store.transition(envelope.task_id, source, target, REASONS["VERIFYING"], self._clock())
            source = target
        return self._summary(envelope)

    def _next_queued(self) -> Optional[Tuple[TaskEnvelope, str]]:
        """Return the next dispatchable task, restoring envelopes on restart."""
        for row in self.store.queued():
            envelope = self._queue.get(row["task_id"])
            if envelope is None:
                envelope = self._restore(row["task_id"])
                if envelope is None:
                    continue
            return envelope, row["state"]
        return None

    def _restore(self, task_id: str) -> Optional[TaskEnvelope]:
        """Rebuild an envelope from durable state (no resubmission, no re-run)."""
        try:
            raw = self.store.envelope(task_id)
        except StoreError:
            return None
        try:
            return TaskEnvelope.from_dict(raw)
        except ContractError:
            return None

    @staticmethod
    def _deadline_passed(deadline: str) -> bool:
        try:
            parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(timezone.utc) >= parsed

    def _hold(self, envelope: TaskEnvelope, reason: str) -> None:
        self.audit.record("scheduler", envelope.task_id, reason, "hold")
        row = self.store.get(envelope.task_id)
        if row is None:
            return
        state = TaskState(row["state"])
        for target in ("HOLD",):
            if can_transition(state, TaskState.HOLD):
                self.store.transition(envelope.task_id, state.value, target, reason, self._clock())
                return

    def _messages(self, envelope: TaskEnvelope) -> List[ChatMessage]:
        payload = dict(envelope.payload or {})
        raw = payload.get("messages")
        if isinstance(raw, list) and raw:
            messages = []
            for turn in raw:
                if not isinstance(turn, dict):
                    raise PolicyViolation("messages must be role/content objects")
                unknown = sorted(set(turn) - {"role", "content"})
                if unknown:
                    raise PolicyViolation("messages carry unexpected fields")
                messages.append(ChatMessage(role=str(turn["role"]), content=str(turn["content"])))
            return messages
        return [ChatMessage(role="user", content=envelope.goal)]

    def _reply_matches(self, reply: ChatReply, provider_name: str, model_id: str) -> bool:
        return (
            reply.provider == provider_name
            and reply.model_id == model_id
            and reply.evidence_class in ("direct", "simulated")
            and isinstance(reply.request_id, str)
            and bool(reply.request_id.strip())
        )

    def _result(self, envelope, attempt_id, provider_name, model_id, reply) -> AgentResult:
        return AgentResult(
            task_id=envelope.task_id,
            attempt_id=attempt_id,
            status="completed",
            model_provider=provider_name,
            model_id=model_id,
            evidence_class=reply.evidence_class,
            typed_result={"text": reply.content},
            child_session_ref=None,
            evidence_refs=(reply.request_id,),
            duration_ms=None,
            usage_if_observed=dict(reply.usage),
            redaction_policy_revision=SCHEMA_VERSION,
            disclosure_level="L0",
        )

    # -- review / cancellation ----------------------------------------------
    def review(self, task_id: str, *, accept: bool) -> str:
        row = self.store.get(task_id)
        if row is None:
            raise StoreError("unknown task")
        state = TaskState(row["state"])
        if state is not TaskState.REVIEW:
            raise VerificationError("task is not awaiting review")
        reason = REASONS["DONE"] if accept else REASONS["FAILED"]
        target = TaskState.DONE if accept else TaskState.FAILED
        self.store.transition(task_id, state.value, target.value, reason, self._clock())
        self._queue.pop(task_id, None)
        return target.value

    def cancel(self, task_id: str) -> str:
        row = self.store.get(task_id)
        if row is None:
            raise StoreError("unknown task")
        state = TaskState(row["state"])
        if state is TaskState.CANCELLED:
            return state.value
        self._queue.pop(task_id, None)
        if state in (TaskState.QUEUED, TaskState.HOLD, TaskState.REVIEW) and can_transition(state, TaskState.CANCELLED):
            self.store.transition(task_id, state.value, TaskState.CANCELLED.value, REASONS["CANCELLED"], self._clock())
            return TaskState.CANCELLED.value
        if can_transition(state, TaskState.HOLD):
            self.store.transition(task_id, state.value, TaskState.HOLD.value, REASONS["CANCELLED"], self._clock())
        for row_pending in self.store.pending():
            if row_pending["task_id"] == task_id and row_pending["state"] in (TaskState.RUNNING.value, TaskState.VERIFYING.value):
                self.store.transition(task_id, row_pending["state"], TaskState.HOLD.value, REASONS["interrupted"], self._clock())
                return TaskState.HOLD.value
        return state.value

    def recover(self) -> List[str]:
        """Move interrupted in-flight tasks back to a safe state on startup."""
        moved: List[str] = []
        for row in self.store.pending():
            state = row["state"]
            if state in (TaskState.RUNNING.value, TaskState.VERIFYING.value):
                self.store.transition(row["task_id"], state, TaskState.HOLD.value, REASONS["interrupted"], self._clock())
                moved.append(row["task_id"])
        for row in self.store.by_state((TaskState.QUEUED.value,)):
            self._queue.setdefault(row["task_id"], None)  # queue not repopulated without the envelope
        return moved

    def result_text(self, task_id: str) -> Optional[str]:
        """Return the recorded local reply text for an owner-side inspection."""
        row = self.store.get(task_id)
        if row is None:
            raise StoreError("unknown task")
        attempts = row.get("attempts") or []
        if not attempts:
            return None
        typed = attempts[-1].get("typed_result") or {}
        text = typed.get("text")
        return text if isinstance(text, str) else None

    def status(self, task_id: str) -> Dict[str, Any]:
        row = self.store.get(task_id)
        if row is None:
            raise StoreError("unknown task")
        return self._summary_from_row(row)

    # -- summaries -----------------------------------------------------------
    def _summary(self, envelope: TaskEnvelope) -> Dict[str, Any]:
        row = self.store.get(envelope.task_id)
        if row is None:
            return {"task_id": envelope.task_id, "state": "MISSING"}
        return self._summary_from_row(row)

    @staticmethod
    def _summary_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
        attempts = row.get("attempts") or []
        latest = attempts[-1] if attempts else {}
        return {
            "task_id": row["task_id"],
            "state": row["state"],
            "reason": row["events"][-1]["reason"] if row["events"] else None,
            "provider": latest.get("model_provider"),
            "model_id": latest.get("model_id"),
            "evidence_class": latest.get("evidence_class"),
            "usage_if_observed": latest.get("usage_if_observed") or {},
            "live_acceptance": "HOLD",
        }

    def close(self) -> None:
        """Release the local state store this core used."""
        self.store.close()

    def __enter__(self) -> "BoruCore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
