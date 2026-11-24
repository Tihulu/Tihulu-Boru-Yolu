"""Localhost polling sync for repository events (issue #8, P8 source slice).

The issue's guidance: *"For localhost pilots prefer polling or manually invoked
sync until securely authenticated ingress is designed."* This module is that
path: an owner-invoked sync that reads through the official connector and never
opens a listener, never inverts the allowlist, and never re-processes an event.

Guarantees:
* only event types on the owner's allowlist are accepted;
* each event id is processed once (bounded, restart-safe idempotency): an
  id that leaves the window is never replayed, and a full registry refuses
  new work instead of forgetting old ids;
* an unknown or malformed event is refused, not silently skipped into work;
* the cursor is monotonic and reported, so a sync is observable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..errors import ConnectorDenied

MAX_EVENTS = 256
#: The seen registry is bounded and never forgets: once it is full, further new
#: ids are refused rather than silently replaying an evicted one.
MAX_SEEN = 8192


@dataclass(frozen=True)
class SyncEvent:
    """One observed event, typed and bounded."""

    event_id: str
    event_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.event_id, str) or not self.event_id.strip() or len(self.event_id) > 128:
            errors.append("event_id must be a bounded non-empty string")
        if not isinstance(self.event_type, str) or not self.event_type.strip() or len(self.event_type) > 64:
            errors.append("event_type must be a bounded non-empty string")
        if not isinstance(self.payload, Mapping):
            errors.append("payload must be a mapping")
        elif len(self.payload) > 32:
            errors.append("payload has too many keys")
        return errors


class EventAllowlist:
    """Owner-declared event types. An empty allowlist accepts nothing."""

    def __init__(self, allowed: Sequence[str]) -> None:
        if not isinstance(allowed, (list, tuple)):
            raise ConnectorDenied("event_allowlist_malformed")
        cleaned = []
        if not allowed:
            raise ConnectorDenied("event_allowlist_empty")
        for value in allowed:
            if not isinstance(value, str) or not value.strip() or len(value) > 64:
                raise ConnectorDenied("event_allowlist_malformed")
            cleaned.append(value.strip())
        if len(set(cleaned)) != len(cleaned):
            raise ConnectorDenied("event_allowlist_duplicate")
        self.allowed: Tuple[str, ...] = tuple(cleaned)

    def permits(self, event_type: str) -> bool:
        return isinstance(event_type, str) and event_type in self.allowed


class PollingSync:
    """Owner-invoked, listener-free event synchronization."""

    def __init__(self, allowlist: EventAllowlist, seen: Optional[Iterable[str]] = None) -> None:
        self.allowlist = allowlist
        self._seen: List[str] = []
        self._seen_set: Set[str] = set()
        # A restored history is bounded exactly like a live one: an oversized
        # checkpoint is refused instead of silently trusted, because the
        # registry's bound is its memory bound.  The bound is enforced **while
        # the checkpoint is being consumed**, not after it has been fully
        # materialized: an unbounded source is read only up to the refusal, so
        # a 10,000-entry checkpoint is stopped at the bound instead of being
        # drained into memory first (N05).
        if seen is not None:
            for event_id in seen:
                if isinstance(event_id, str) and event_id and event_id not in self._seen_set:
                    # The bound applies to the registry as it is filled: the
                    # entry that would exceed it is refused as it arrives, so an
                    # oversized source is never drained into memory first.
                    if len(self._seen) >= MAX_SEEN:
                        raise ConnectorDenied("restored history exceeds the bounded registry")
                    self._seen.append(event_id)
                    self._seen_set.add(event_id)

    @property
    def seen(self) -> Tuple[str, ...]:
        return tuple(self._seen)

    def normalize(self, raw_events: Any) -> List[SyncEvent]:
        """Parse a provider payload into typed, allowlisted events."""
        if not isinstance(raw_events, list):
            raise ConnectorDenied("events_malformed")
        if len(raw_events) > MAX_EVENTS:
            raise ConnectorDenied("events_too_many")
        parsed: List[SyncEvent] = []
        for entry in raw_events:
            if not isinstance(entry, Mapping):
                raise ConnectorDenied("events_malformed")
            unknown = sorted(set(entry) - {"id", "type", "payload"})
            if unknown:
                raise ConnectorDenied("events_malformed")
            event = SyncEvent(event_id=str(entry.get("id", "")), event_type=str(entry.get("type", "")),
                              payload=dict(entry.get("payload") or {}))
            if event.validate():
                raise ConnectorDenied("events_malformed")
            if not self.allowlist.permits(event.event_type):
                raise ConnectorDenied("event_type_not_allowed")
            if event.event_id in self._seen_set:
                continue  # already processed: idempotent, never rework
            parsed.append(event)
        return parsed

    def accept(self, events: Sequence[SyncEvent]) -> List[SyncEvent]:
        """Mark events as processed and return the newly accepted ones."""
        fresh: List[SyncEvent] = []
        for event in events:
            if event.event_id in self._seen_set:
                continue
            self._remember(event.event_id)
            fresh.append(event)
        return fresh

    def _remember(self, event_id: str) -> None:
        """Record one processed id; a full registry refuses, never forgets."""
        if len(self._seen) >= MAX_SEEN:
            raise ConnectorDenied("seen_registry_full")
        self._seen.append(event_id)
        self._seen_set.add(event_id)
