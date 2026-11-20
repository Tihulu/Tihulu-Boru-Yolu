"""Deterministic task state machine.

Lifecycle (docs/ARCHITECTURE.md):

    CREATED -> CLASSIFIED -> PLANNED -> QUEUED -> RUNNING -> VERIFYING
           -> REVIEW -> DONE

``FAILED``, ``CANCELLED`` are terminal, ``HOLD`` is a resumable pause.
An agent's self-report can never move a task to ``DONE``: only
``BoruCore.verify`` promotes DONE, and only from ``REVIEW``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .errors import InvalidTransition
from .types import SCHEMA_VERSION, AgentResult, TaskEnvelope


class TaskState(str, Enum):
    CREATED = "CREATED"
    CLASSIFIED = "CLASSIFIED"
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    HOLD = "HOLD"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


#: Allowed source -> target transitions.  Anything absent is rejected.
ALLOWED_TRANSITIONS: Dict[TaskState, Tuple[TaskState, ...]] = {
    TaskState.CREATED: (TaskState.CLASSIFIED, TaskState.HOLD, TaskState.CANCELLED, TaskState.FAILED),
    TaskState.CLASSIFIED: (TaskState.PLANNED, TaskState.HOLD, TaskState.CANCELLED, TaskState.FAILED),
    TaskState.PLANNED: (TaskState.QUEUED, TaskState.CLASSIFIED, TaskState.HOLD, TaskState.CANCELLED, TaskState.FAILED),
    TaskState.QUEUED: (TaskState.RUNNING, TaskState.CANCELLED, TaskState.HOLD, TaskState.FAILED),
    TaskState.RUNNING: (TaskState.VERIFYING, TaskState.FAILED, TaskState.CANCELLED, TaskState.HOLD),
    TaskState.VERIFYING: (TaskState.REVIEW, TaskState.FAILED, TaskState.HOLD, TaskState.CANCELLED),
    TaskState.REVIEW: (TaskState.DONE, TaskState.FAILED, TaskState.HOLD, TaskState.CANCELLED),
    TaskState.DONE: (),
    TaskState.FAILED: (TaskState.CLASSIFIED,),
    TaskState.CANCELLED: (),
    TaskState.HOLD: (TaskState.CLASSIFIED, TaskState.PLANNED, TaskState.QUEUED, TaskState.CANCELLED, TaskState.FAILED),
}

TERMINAL_STATES = frozenset({TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED})


def can_transition(source: TaskState, target: TaskState) -> bool:
    """Return True only for an explicitly allowed transition."""
    return target in ALLOWED_TRANSITIONS.get(source, ())


@dataclass
class TaskRecord:
    """Mutable per-task bookkeeping owned by Boru Core."""

    task_id: str
    envelope: TaskEnvelope
    state: TaskState = TaskState.CREATED
    attempts: List[AgentResult] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = SCHEMA_VERSION

    def can_transition_to(self, target: TaskState) -> bool:
        return can_transition(self.state, target)

    def transition(self, target: TaskState, reason: str, at: Optional[str] = None) -> TaskRecord:
        """Apply an allowed transition and record an audit event."""
        if self.state is target:
            return self
        if not self.can_transition_to(target):
            raise InvalidTransition(
                "illegal transition {} -> {}".format(self.state.value, target.value)
            )
        stamp = at or utc_now()
        self.events.append(
            {
                "at": stamp,
                "from": self.state.value,
                "to": target.value,
                "reason": reason,
            }
        )
        self.state = target
        self.updated_at = stamp
        return self


def utc_now() -> str:
    """ISO-8601 UTC timestamp (second precision) for local audit records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
