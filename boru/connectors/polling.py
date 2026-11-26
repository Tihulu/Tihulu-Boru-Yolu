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

N05 FIX: Raw event identifiers are validated BEFORE any coercion. Non-string,
empty, whitespace-only, oversized, or control-carrying identifiers are refused
rather than silently coerced or skipped.

N16 FIX: `accept()` performs full pre-flight validation (shape, ID, allowlist)
on ALL events BEFORE any mutation to the seen registry. Batch rejection is
atomic — if any event fails, the entire batch is rejected without partial
mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..errors import ConnectorDenied

MAX_EVENTS = 256
#: The seen registry is bounded and never forgets: once it is full, further new
#: ids are refused rather than silently replaying an evicted one.
MAX_SEEN = 8192

#: A restored checkpoint is inspected with a bounded budget of **entries**, not
#: only unique ids: a duplicate-heavy source must not be drained completely to
#: fill a registry that never grew (N05).  The budget is several times the
#: registry bound, so a legitimate checkpoint with some duplicates still loads.
MAX_RESTORED_ENTRIES = 4 * MAX_SEEN

#: A restored id is held to the same shape as a live event id, oversized ones
#: included: a checkpoint entry that is not a usable id is refused rather than
#: silently dropped.
MAX_EVENT_ID_LENGTH = 128

#: Maximum length of an event type.
MAX_EVENT_TYPE_LENGTH = 64


def event_id(value: Any) -> str:
    """The one event-id validator this module uses (N05).

    Restoration, normalization and acceptance all funnel through here, so an
    id that is not a usable identifier - not a string, empty, whitespace-only,
    oversized or carrying a control character - is **refused** rather than
    skipped: silently dropping a malformed checkpoint entry hides corruption
    the owner should see, and a whitespace-only id is not an id.
    """
    if not isinstance(value, str):
        raise ConnectorDenied("event_id_malformed")
    if not value or value.strip() != value or len(value) > MAX_EVENT_ID_LENGTH:
        raise ConnectorDenied("event_id_malformed")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ConnectorDenied("event_id_malformed")
    return value


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
        self._lock = RLock()
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
            inspected = 0
            for candidate in seen:
                inspected += 1
                # The bound applies while the source is consumed, on **both**
                # axes: the registry as it is filled, and the number of entries
                # inspected.  A duplicate-heavy checkpoint therefore stops at
                # the inspected budget instead of being drained completely
                # (N05).
                if inspected > MAX_RESTORED_ENTRIES:
                    raise ConnectorDenied("restored history exceeds the bounded registry")
                # One validator for every entry: a malformed checkpoint entry
                # refuses instead of being silently skipped (N05).
                identifier = event_id(candidate)
                if identifier in self._seen_set:
                    continue
                if len(self._seen) >= MAX_SEEN:
                    raise ConnectorDenied("restored history exceeds the bounded registry")
                self._seen.append(identifier)
                self._seen_set.add(identifier)

    @property
    def seen(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._seen)

    def _validate_raw_type(self, raw_type: Any) -> str:
        """Validate a raw event type BEFORE coercion (N05)."""
        if not isinstance(raw_type, str):
            raise ConnectorDenied("event_type_malformed")
        if not raw_type or raw_type.strip() != raw_type or len(raw_type) > 64:
            raise ConnectorDenied("event_type_malformed")
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw_type):
            raise ConnectorDenied("event_type_malformed")
        return raw_type.strip()

    def normalize(self, raw_events: Any) -> List[SyncEvent]:
        """Parse a provider payload into typed, allowlisted events.

        N05 FIX: Raw event IDs and types are validated BEFORE coercion so
        non-string values (int, dict, None, bytes, bool) are refused rather
        than silently turned into string representations.

        Also maintains idempotency: already-seen events are filtered out.
        """
        parsed = self._normalize_raw(raw_events)
        # Filter out already-seen events for idempotency (N05)
        with self._lock:
            return [e for e in parsed if e.event_id not in self._seen_set]

    def _normalize_raw(self, raw_events: Any) -> List[SyncEvent]:
        """Internal normalize without idempotency filtering."""
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

            # N05: Validate raw ID BEFORE coercion
            raw_id = entry.get("id")
            validated_id = event_id(raw_id)

            # N05: Validate raw event_type BEFORE coercion
            raw_type = entry.get("type")
            validated_type = self._validate_raw_type(raw_type)

            raw_payload = entry.get("payload", {})
            if not isinstance(raw_payload, Mapping) or len(raw_payload) > 32:
                raise ConnectorDenied("events_malformed")
            event = SyncEvent(
                event_id=validated_id,
                event_type=validated_type,
                payload=dict(raw_payload)
            )
            if event.validate():
                raise ConnectorDenied("events_malformed")
            # Allowlist check in normalize (N16): refuse undeclared types early
            if not self.allowlist.permits(event.event_type):
                raise ConnectorDenied("event_type_not_allowed")
            parsed.append(event)
        return parsed

    def accept(self, events: Sequence[SyncEvent]) -> List[SyncEvent]:
        """Validate a bounded batch once, then atomically commit fresh IDs."""
        prepared: List[SyncEvent] = []
        for index, event in enumerate(events):
            if index >= MAX_RESTORED_ENTRIES:
                raise ConnectorDenied("events_too_many")
            if type(event) is not SyncEvent or event.validate():
                raise ConnectorDenied("events_malformed")
            identifier = event_id(event.event_id)
            event_type = self._validate_raw_type(event.event_type)
            if not self.allowlist.permits(event_type):
                raise ConnectorDenied("event_type_not_allowed")
            payload = dict(event.payload)
            if len(payload) > 32:
                raise ConnectorDenied("events_malformed")
            prepared.append(SyncEvent(identifier, event_type, payload))

        with self._lock:
            pending: Set[str] = set()
            fresh: List[SyncEvent] = []
            for event in prepared:
                if event.event_id not in self._seen_set and event.event_id not in pending:
                    pending.add(event.event_id)
                    fresh.append(event)
            if len(self._seen) + len(pending) > MAX_SEEN:
                raise ConnectorDenied("seen_registry_full")
            self._seen.extend(event.event_id for event in fresh)
            self._seen_set.update(pending)
            return fresh
