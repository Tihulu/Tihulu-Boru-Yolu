"""Versioned typed contracts for Boru Core tasks and results.

``TaskEnvelope`` and ``AgentResult`` are the only currency exchanged between
the scheduler, providers and optional adapters.  Both directions reject
unknown keys so a private host field can never be smuggled through a well
meaning adapter, and ``AgentResult`` refuses keys that would carry raw private
host state (raw stdout, environment, paths, credentials) across a boundary.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence, Tuple

from .errors import ContractError
from .policy import (
    DISCLOSURE_LEVELS,
    EXECUTION_PROFILES,
    INFERENCE_SCOPES,
    OPTIMIZATION_MODES,
    DISCLOSURE_POLICIES,
)

SCHEMA_VERSION = 1
#: Typed payloads are shallow and small: depth, keys and values are bounded so
#: a nested structure cannot smuggle unbounded or private content through.
MAX_RESULT_DEPTH = 2
MAX_PAYLOAD_KEYS = 32
MAX_PAYLOAD_STRING_CHARS = 512
MAX_PAYLOAD_INT = 10 ** 12
EVIDENCE_CLASSES: Tuple[str, ...] = ("direct", "user_reported", "simulated", "unknown")
COMPLEXITY_LEVELS: Tuple[str, ...] = ("simple", "medium", "difficult")
RESULT_STATUSES: Tuple[str, ...] = ("completed", "failed", "cancelled", "timeout")

# Keys that may never appear inside a typed result: each one would carry
# private host state across a trust boundary (ADR-0004 / Privacy Bridge).
FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "raw_stdout",
        "raw_stderr",
        "raw_output",
        "raw_log",
        "raw_traceback",
        "environment",
        "env",
        "home_path",
        "home_directory",
        "username",
        "user_home",
        "api_key",
        "token",
        "credential",
        "secrets",
        "file_contents",
        "directory_listing",
        "process_list",
        "device_list",
    }
)


def _names(cls) -> Tuple[str, ...]:
    return tuple(f.name for f in fields(cls))


def _payload_error(value: Any, depth: int = 0) -> Optional[str]:
    """Reject anything that is not bounded, typed and free of private keys.

    The forbidden key check is recursive: nesting a private field inside an
    innocent key does not launder it.
    """
    if depth > MAX_RESULT_DEPTH:
        return "payload is nested too deeply"
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if not math.isfinite(value) or not 0 <= value <= MAX_PAYLOAD_INT:
            return "count is out of the bounded range"
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "float must be finite"
    if isinstance(value, str):
        if len(value) > MAX_PAYLOAD_STRING_CHARS:
            return "string exceeds the bounded length"
        if any(character in value for character in ("\n", "\r", "\x00")):
            return "string contains control characters"
        return None
    if isinstance(value, Mapping):
        if len(value) > MAX_PAYLOAD_KEYS:
            return "object has too many keys"
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                return "object key is oversized"
            if key in FORBIDDEN_RESULT_KEYS:
                return "private field is not releasable at any depth: " + key
            error = _payload_error(item, depth + 1)
            if error:
                return error
        return None
    return "unsupported payload type"


def _string_tuple_errors(value: Any, label: str) -> list:
    """Validate a tuple of bounded, non-empty strings."""
    if not isinstance(value, tuple):
        return [label + " must be a tuple of strings"]
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 64:
            return [label + " entries must be bounded non-empty strings"]
    return []


def _deadline_errors(value: Any) -> list:
    """Validate an ISO-8601 UTC deadline without guessing its meaning."""
    errors: list = []
    if not isinstance(value, str):
        return ["deadline must be a string"]
    if len(value) > 40:
        errors.append("deadline exceeds the bounded length")
        return errors
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ["deadline must be an ISO-8601 UTC timestamp"]
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        errors.append("deadline must carry an explicit UTC offset")
    return errors


def _reject_unknown(obj: Mapping[str, Any], allowed: Sequence[str], where: str) -> None:
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise ContractError(where + ": unknown field(s) " + ", ".join(unknown))


def _check_str(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(label + " must be a string")
    if not allow_empty and not value.strip():
        raise ContractError(label + " must not be empty")
    return value


def _check_optional_positive(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ContractError(label + " must be a positive number")
    return float(value)


@dataclass(frozen=True)
class TaskEnvelope:
    """A unit of work handed to Boru Core."""

    task_id: str
    goal: str
    complexity: str = "simple"
    capability_tags: Tuple[str, ...] = ()
    priority: int = 0
    parent_task_id: Optional[str] = None
    workflow_revision: int = SCHEMA_VERSION
    routing_mode: str = "AUTO"
    inference_scope: str = "LOCAL_ONLY"
    execution_profile: str = "LOCAL_ISOLATED"
    disclosure_policy: str = "MINIMUM_NECESSARY"
    allowed_agent_ids: Tuple[str, ...] = ()
    max_parallel: int = 1
    token_budget: Optional[int] = None
    cost_budget_usd: Optional[float] = None
    max_attempts: int = 1
    idempotency_key: Optional[str] = None
    requester_identity: str = "owner"
    consent_reference: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    # Optional owner-side scheduling hints (never a permission grant).
    deadline: Optional[str] = None
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list:
        """Return a list of contract violations; empty means well formed."""
        errors: list = []
        for name, value in (
            ("task_id", self.task_id),
            ("goal", self.goal),
            ("requester_identity", self.requester_identity),
        ):
            try:
                _check_str(value, name)
            except ContractError as exc:
                errors.append(str(exc))
        if self.complexity not in COMPLEXITY_LEVELS:
            errors.append("unknown complexity")
        if self.routing_mode not in OPTIMIZATION_MODES:
            errors.append("unknown routing_mode")
        if self.inference_scope not in INFERENCE_SCOPES:
            errors.append("unknown inference_scope")
        if self.execution_profile not in EXECUTION_PROFILES:
            errors.append("unknown execution_profile")
        if self.disclosure_policy not in DISCLOSURE_POLICIES:
            errors.append("unknown disclosure_policy")
        if isinstance(self.max_parallel, bool) or not isinstance(self.max_parallel, int) or self.max_parallel < 1:
            errors.append("max_parallel must be a positive integer")
        errors.extend(_string_tuple_errors(self.capability_tags, "capability_tags"))
        errors.extend(_string_tuple_errors(self.allowed_agent_ids, "allowed_agent_ids"))
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            errors.append("max_attempts must be a positive integer")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            errors.append("priority must be an integer")
        try:
            _check_optional_positive(self.token_budget, "token_budget")
            _check_optional_positive(self.cost_budget_usd, "cost_budget_usd")
        except ContractError as exc:
            errors.append(str(exc))
        if self.deadline is not None:
            errors.extend(_deadline_errors(self.deadline))
        if (self.selected_provider is None) != (self.selected_model is None):
            errors.append("selected_provider and selected_model must be provided together")
        for name, value in (("selected_provider", self.selected_provider), ("selected_model", self.selected_model)):
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 128):
                errors.append(name + " must be a bounded non-empty string")
        leak = sorted(set(self.payload) & FORBIDDEN_RESULT_KEYS)
        if leak:
            errors.append("payload may not carry private fields: " + ", ".join(leak))
        if self.schema_version != SCHEMA_VERSION:
            errors.append("unsupported schema_version")
        return errors

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ContractError("; ".join(errors))

    def to_dict(self) -> dict:
        data = {}
        for name in _names(TaskEnvelope):
            data[name] = getattr(self, name)
        data["capability_tags"] = list(self.capability_tags)
        data["allowed_agent_ids"] = list(self.allowed_agent_ids)
        data["payload"] = dict(self.payload)
        return data

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "TaskEnvelope":
        if not isinstance(obj, Mapping):
            raise ContractError("task envelope must be a mapping")
        _reject_unknown(obj, _names(cls), "TaskEnvelope")
        _required = ("task_id", "goal")
        for name in _required:
            if name not in obj:
                raise ContractError("TaskEnvelope: missing " + name)
        kwargs = dict(obj)
        kwargs["capability_tags"] = tuple(obj.get("capability_tags", ()))
        kwargs["allowed_agent_ids"] = tuple(obj.get("allowed_agent_ids", ()))
        kwargs["payload"] = dict(obj.get("payload", {}))
        envelope = cls(**kwargs)  # type: ignore[arg-type]
        envelope.assert_valid()
        return envelope

    #: Axes a child task may never override: permission is inherited, never widened.
    _PROTECTED_AXES = frozenset(
        {"routing_mode", "inference_scope", "execution_profile", "disclosure_policy"}
    )

    def child(self, task_id: str, goal: str, **overrides: Any) -> "TaskEnvelope":
        """Derive a child task that inherits this task's policy axes.

        Attempting to override any protected axis raises ``ContractError``: a
        parent cannot grant a child more inference, execution or disclosure
        rights than it holds.
        """
        widened = sorted(self._PROTECTED_AXES & set(overrides))
        if widened:
            raise ContractError("child task may not override policy axes: " + ", ".join(widened))
        for name in ("token_budget", "cost_budget_usd", "max_parallel", "max_attempts"):
            if name in overrides and overrides[name] is not None:
                current = getattr(self, name)
                if current is not None and overrides[name] > current:
                    raise ContractError(name + " cannot exceed the parent limit")
        base = dict(
            parent_task_id=self.task_id,
            complexity=self.complexity,
            capability_tags=self.capability_tags,
            routing_mode=self.routing_mode,
            inference_scope=self.inference_scope,
            execution_profile=self.execution_profile,
            disclosure_policy=self.disclosure_policy,
            token_budget=self.token_budget,
            cost_budget_usd=self.cost_budget_usd,
            requester_identity=self.requester_identity,
        )
        base.update(overrides)
        return TaskEnvelope(task_id=task_id, goal=goal, **base)


@dataclass(frozen=True)
class AgentResult:
    """Verified outcome of one task attempt."""

    task_id: str
    attempt_id: str
    status: str
    model_provider: str = ""
    model_id: str = ""
    evidence_class: str = "unknown"
    typed_result: Mapping[str, Any] = field(default_factory=dict)
    child_session_ref: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()
    duration_ms: Optional[int] = None
    usage_if_observed: Mapping[str, Any] = field(default_factory=dict)
    redaction_policy_revision: int = SCHEMA_VERSION
    authorization_receipt_id: Optional[str] = None
    disclosure_level: str = "L0"
    error_kind: Optional[str] = None
    error_message: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def validate(self, max_result_fields: int = 4) -> list:
        errors: list = []
        for name, value in (("task_id", self.task_id), ("attempt_id", self.attempt_id)):
            try:
                _check_str(value, name)
            except ContractError as exc:
                errors.append(str(exc))
        if self.status not in RESULT_STATUSES:
            errors.append("unknown result status")
        if self.evidence_class not in EVIDENCE_CLASSES:
            errors.append("unknown evidence class")
        if self.disclosure_level not in DISCLOSURE_LEVELS:
            errors.append("unknown disclosure level")
        if self.status == "completed":
            if not self.model_provider.strip() or not self.model_id.strip():
                errors.append("completed result must name provider and model")
        leak = sorted(set(self.typed_result) & FORBIDDEN_RESULT_KEYS)
        if leak:
            errors.append("typed_result may not carry private fields: " + ", ".join(leak))
        payload_error = _payload_error(dict(self.typed_result))
        if payload_error:
            errors.append("typed_result rejected: " + payload_error)
        usage_error = _payload_error(dict(self.usage_if_observed))
        if usage_error:
            errors.append("usage_if_observed rejected: " + usage_error)
        if len(self.typed_result) > max_result_fields:
            errors.append("typed_result exceeds max_result_fields")
        if self.schema_version != SCHEMA_VERSION:
            errors.append("unsupported schema_version")
        if self.redaction_policy_revision != SCHEMA_VERSION:
            errors.append("unsupported redaction_policy_revision")
        return errors

    def assert_valid(self, max_result_fields: int = 4) -> None:
        errors = self.validate(max_result_fields)
        if errors:
            raise ContractError("; ".join(errors))

    def to_dict(self) -> dict:
        data = {}
        for name in _names(AgentResult):
            data[name] = getattr(self, name)
        data["evidence_refs"] = list(self.evidence_refs)
        data["typed_result"] = dict(self.typed_result)
        data["usage_if_observed"] = dict(self.usage_if_observed)
        return data

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "AgentResult":
        if not isinstance(obj, Mapping):
            raise ContractError("agent result must be a mapping")
        _reject_unknown(obj, _names(cls), "AgentResult")
        missing = [n for n in ("task_id", "attempt_id", "status") if n not in obj]
        if missing:
            raise ContractError("AgentResult: missing field(s) " + ", ".join(missing))
        kwargs = dict(obj)
        kwargs["evidence_refs"] = tuple(obj.get("evidence_refs", ()))
        kwargs["typed_result"] = dict(obj.get("typed_result", {}))
        kwargs["usage_if_observed"] = dict(obj.get("usage_if_observed", {}))
        return cls(**kwargs)  # type: ignore[arg-type]
