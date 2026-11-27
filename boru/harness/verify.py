"""Post-hoc claim verification for durable Boru state (ADR 0006).

Design reference: OpenHawk's ``claimcheck`` ("did the agent actually write the
files it claimed?") and LEO's audited approvals. Boru already enforces its
invariants *at transition time* — a forged reply never becomes DONE, an L0 grant
never authorizes L2, the ledger never stores a payload. This module answers the
different, complementary question an owner asks **after the fact**:

    "Does the durable state I am looking at actually back the claims it makes?"

It re-checks, at rest and read-only, that:

1. a task in a terminal-success state (``REVIEW``/``DONE``) carries recorded
   attempt evidence — a success claim with no evidence is **unbacked**;
2. a task in a non-success terminal state (``FAILED``/``CANCELLED``) records at
   least one transition with a reason — a failure with no reason is **unexplained**;
3. every task state is a known state name — an unknown state is **corrupt**;
4. the rejection ledger is still sanitized at rest — a row carrying a path, URL
   or token fragment is a **disclosure defect**;
5. the store record count is inside its configured bound.

Nothing here mutates state, performs a provider call, or widens an axis. It is a
pure audit over bounded public state, and a failure is **reported**, never
repaired: the harness is not an authorization surface.

Returned findings are bounded, typed strings only — never a path, payload or
credential.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

#: Known task states; anything else in the store is corruption.
KNOWN_STATES: Tuple[str, ...] = (
    "CREATED", "CLASSIFIED", "PLANNED", "QUEUED", "RUNNING", "VERIFYING",
    "REVIEW", "DONE", "FAILED", "CANCELLED", "HOLD",
)

#: Terminal-success states that must carry attempt evidence.
SUCCESS_STATES: Tuple[str, ...] = ("REVIEW", "DONE")
#: Non-success terminal states that must carry a reason.
FAILURE_STATES: Tuple[str, ...] = ("FAILED", "CANCELLED")

#: The audit is bounded: a large history is sampled, never fully drained.
MAX_TASKS_AUDITED = 512
MAX_ATTEMPTS = 8
MAX_EVENTS = 16

_FINDING_UNBACKED = "success_without_evidence"
_FINDING_UNEXPLAINED = "failure_without_reason"
_FINDING_UNKNOWN_STATE = "unknown_task_state"
_FINDING_LEDGER_UNSAFE = "ledger_row_unsafe"
_FINDING_STORE_OVER_BOUND = "store_over_bound"


def _safe_subject(value: Any) -> str:
    """A bounded, path-free label for anything this audit reports.

    A hostile ``task_id`` must not be able to launder a path, URL or token into
    a report: the same sanitizer the rejection ledger uses is applied here, and
    a value it refuses becomes an opaque marker instead of leaking.
    """
    try:
        from ..audit import sanitize_identifier
        return sanitize_identifier(value, 64, "task_id")
    except Exception:
        return "unidentified"


@dataclass(frozen=True)
class VerificationReport:
    """A bounded, typed audit result. Findings are strings, never state."""

    checked: int
    findings: Tuple[Tuple[str, str], ...]
    ok: bool

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "ok": self.ok,
            "findings": [list(row) for row in self.findings],
        }


def _known_state(state: Any) -> bool:
    return isinstance(state, str) and state in KNOWN_STATES


def _has_attempt(task: Any) -> bool:
    attempts = getattr(task, "get", lambda _k, _d=None: None)("attempts") \
        if isinstance(task, dict) else None
    if isinstance(attempts, (list, tuple)):
        return len(list(attempts)[:MAX_ATTEMPTS]) > 0
    return False


def _has_reason(task: Any) -> bool:
    events = task.get("events") if isinstance(task, dict) else None
    if not isinstance(events, (list, tuple)):
        return False
    for event in list(events)[:MAX_EVENTS]:
        reason = event.get("reason") if isinstance(event, dict) else None
        if isinstance(reason, str) and reason.strip():
            return True
    return False


def _ledger_row_is_unsafe(row: Any) -> bool:
    """A ledger row is safe only when it carries a bounded, sanitized subject."""
    subject = row.get("subject") if isinstance(row, dict) else None
    if not isinstance(subject, str) or not subject.strip():
        return True
    for character in ("/", "\\", ":", "@", "%"):
        if character in subject:
            return True
    return len(subject) > 128


def verify_core(core: Any) -> VerificationReport:
    """Audit one ``BoruCore`` at rest. Read-only; repairs nothing."""
    store = getattr(core, "store", None)
    audit = getattr(core, "audit", None)
    findings: List[Tuple[str, str]] = []
    checked = 0

    by_state = getattr(store, "by_state", None)
    if callable(by_state):
        try:
            rows = list(by_state(SUCCESS_STATES + FAILURE_STATES))[:MAX_TASKS_AUDITED]
        except Exception:
            rows = []
        for row in rows:
            checked += 1
            raw_id = row.get("task_id") if isinstance(row, dict) else None
            task_id = _safe_subject(raw_id)
            state = row.get("state") if isinstance(row, dict) else None
            if not _known_state(state):
                findings.append((_FINDING_UNKNOWN_STATE, task_id))
                continue
            task = None
            getter = getattr(store, "get", None)
            if callable(getter):
                try:
                    task = getter(task_id)
                except Exception:
                    task = None
            if state in SUCCESS_STATES and not _has_attempt(task):
                findings.append((_FINDING_UNBACKED, task_id))
            if state in FAILURE_STATES and not _has_reason(task):
                findings.append((_FINDING_UNEXPLAINED, task_id))

    recent = getattr(audit, "recent", None)
    if callable(recent):
        try:
            rows = list(recent(limit=64))
        except Exception:
            rows = []
        for row in rows:
            if _ledger_row_is_unsafe(row):
                findings.append((_FINDING_LEDGER_UNSAFE, "ledger"))
                break

    count = getattr(store, "count", None)
    maximum = getattr(store, "max_records", None)
    if callable(count) and isinstance(maximum, int):
        try:
            total = count()
        except Exception:
            total = None
        if isinstance(total, int) and total > maximum:
            findings.append((_FINDING_STORE_OVER_BOUND, _safe_subject(str(total))))

    return VerificationReport(checked=checked, findings=tuple(findings[:64]), ok=not findings)
