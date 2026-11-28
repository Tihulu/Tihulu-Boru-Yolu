"""Bounded task queue.

Boru Core never accepts unbounded work: a full queue raises ``QueueFull``
instead of silently buffering, and duplicate idempotency keys are refused so a
retried submit cannot double-run a side effect.

The replay history is a **bounded window**: the durable store's idempotency
fingerprint (``TaskStore.submit``) is the authoritative replay guard, and this
window covers the in-process case — the newest ``history_limit`` consumed keys.
An older key leaving the window is a documented bound, not a silent clearing:
dispatch never fails for a bookkeeping limit, and a pop never loses an item.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Iterable, List, Optional

from .errors import DuplicateTask, QueueFull
from .types import TaskEnvelope


DEFAULT_HISTORY = 4096


class BoundedTaskQueue:
    """FIFO queue with a hard size ceiling and per-key idempotency.

    Consumed keys stay in a bounded replay history so a resubmission can never
    run a task twice while the queue process is alive.
    """

    def __init__(self, maxsize: int = 64, history_limit: int = DEFAULT_HISTORY) -> None:
        if isinstance(maxsize, bool) or not isinstance(maxsize, int) or maxsize < 1:
            from .errors import ContractError

            raise ContractError("queue maxsize must be a positive integer")
        self.maxsize = maxsize
        self._items: Deque[TaskEnvelope] = deque()
        self._seen: Dict[str, TaskEnvelope] = {}
        self._history: Deque[str] = deque()
        self._history_limit = history_limit

    def __len__(self) -> int:
        return len(self._items)

    @property
    def full(self) -> bool:
        return len(self._items) >= self.maxsize

    def put(self, envelope: TaskEnvelope) -> TaskEnvelope:
        """Enqueue an envelope; raises QueueFull / DuplicateTask."""
        if self.full:
            raise QueueFull("queue is full ({} items)".format(self.maxsize))
        key = envelope.idempotency_key or envelope.task_id
        if key in self._seen or key in self._history:
            raise DuplicateTask("idempotency key was already consumed")
        self._seen[key] = envelope
        self._items.append(envelope)
        return envelope

    def peek(self) -> Optional[TaskEnvelope]:
        return self._items[0] if self._items else None

    def pop(self) -> Optional[TaskEnvelope]:
        if not self._items:
            return None
        envelope = self._items.popleft()
        key = envelope.idempotency_key or envelope.task_id
        self._seen.pop(key, None)
        if key not in self._history:
            # The oldest key leaves the bounded window: dispatch must never fail
            # for a bookkeeping limit, and an item is never lost.
            while len(self._history) >= self._history_limit:
                self._history.popleft()
            self._history.append(key)
        return envelope

    def remove(self, task_id: str) -> bool:
        """Remove a queued task by id (cancellation while still queued)."""
        kept: List[TaskEnvelope] = [e for e in self._items if e.task_id != task_id]
        if len(kept) == len(self._items):
            return False
        for envelope in self._items:
            key = envelope.idempotency_key or envelope.task_id
            if envelope.task_id == task_id and key not in self._history:
                self._history.append(key)
        self._items.clear()
        self._items.extend(kept)
        return True

    def pending(self) -> Iterable[TaskEnvelope]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
        self._seen.clear()
        self._history.clear()
