"""Centralised request snapshot for connector entry points.

All externally-connected provider entry points must follow the same pattern:

1. **Read the credential once** (``_token_value()``) and keep that exact
   snapshot for the entire request — fingerprint, verify, transmit.  A
   rotation mid-request must never cause the connector to send a credential
   that was never verified (F07/N02).

2. **Snapshot the mutable request data** (``payload`` and ``body``) **before**
   any authorization exchange runs.  The snapshot is an immutable, bounded
   copy that preserves arrays and objects; after the snapshot is taken the
   caller's original mapping may be mutated freely and it will not change what
   reaches the transport (N12).

3. **Validate the snapshot** against the grant (slots, write-body contracts,
   dispatch-body schema).  Only validated slots are used to build the
   official endpoint.

4. **Charge all authorization traffic** against a bounded instance-level
   budget so identity verification and ownership lookups cannot flood the
   connector (N06).

5. **Verify the credential matches** the grant's account once, then
   cache the (token-fingerprint, account) pair per-instance so subsequent
   grants naming the same account behind the same token are accepted,
   but a different account behind the same token is re-verified (F07).

6. **For run/pipeline operations** — establish ownership from the provider's
   own metadata (not the caller's claim), key the cache by the complete
   authorization context (repository, granted reference, account, credential
   fingerprint, workflow, run id), and enforce a bounded TTL (N07).

7. **For merge operations** — read the pull/merge request's own target
   reference from trusted provider metadata and verify it matches the
   grant's reference before allowing the merge (N13).

8. **For rerun/schedule operations** — address the verified pipeline, never
   an unchecked schedule resource (N14).

This module provides:

- ``RequestSnapshot(value, max_depth, max_keys, max_items)`` — bounded,
  immutable deep-copy of a validated request body; preserves arrays and
  objects as tuples so the snapshot is hashable and cannot be mutated.

- ``snapshot_body(body)`` — thin wrapper used by both providers to
  snapshot the ``body`` parameter at the call site.

- ``snapshot_payload(payload)`` — thin wrapper for the ``payload`` parameter
  on entry points that carry payload (e.g. ``list_workflows_typed``).

- ``snapshot_credentials(token_env)`` — reads the credential **once** and
  returns ``(fingerprint, token)``; ``fingerprint`` is the stable SHA-256
  of ``(provider, token)``.  The same token value is used for fingerprint,
  verify and transmit.

- ``check_authorization_traffic(counter, max_requests)`` — bounded counter
  shared by all authorization paths (identity + ownership).  Returns a
  typed reason when exhausted.

Usage (provider entry point):

.. code-block:: python

    def typed_entry(self, grant, payload=None, ...):
        # 1. Grant check (no transport)
        allowed, reason = self.check(grant, "list_workflows")
        if not allowed:
            raise ConnectorDenied(reason)
        # 2. Central snapshot of the mutable request (before any auth)
        snap = snapshot_payload(payload)
        # 3. Credential snapshot: one read, one fingerprint
        token = self._token_value()
        # 4. Authorization
        self._require_account_identity(grant, token)
        # 5. Validate snapshot against grant
        slots = check_call(grant, "list_workflows", snap or {}, ...)
        # 6. Reserve call (N06)
        reason = self._reserve_call(grant, "list_workflows")
        if reason:
            raise ConnectorDenied(reason)
        # 7. Exchange: transmit the snapshot, not the original
        ...
"""
from __future__ import annotations

import hashlib
import threading
from typing import Any, Dict, Mapping, Optional, Tuple


# --- Bounded deep-copy (immutable snapshot) --------------------------------

#: Maximum nesting depth for snapshots.
MAX_SNAPSHOT_DEPTH = 3

#: Maximum keys in a mapped snapshot.
_MAX_SNAPSHOT_KEYS = 256

#: Maximum items in a sequence snapshot.
_MAX_SNAPSHOT_ITEMS = 256


def snapshot(value: Any, *, depth: int = 0) -> Any:
    """Return a **bounded immutable copy** of a validated request value.

    Mappings become sorted tuples of ``(key, snapshot(value))`` pairs;
    sequences become _ArrayMarker tuples of snapshots.  This preserves arrays
    and objects exactly and unambiguously, while making the result hashable
    and impossible to mutate.

    A ``DepthExceeded`` sentinel is returned when the depth limit
    is hit, so the caller can raise ``ConnectorDenied`` deterministically.
    """
    if depth > MAX_SNAPSHOT_DEPTH:
        return _DepthExceeded()
    if isinstance(value, Mapping):
        items = list(value.items())
        if len(items) > _MAX_SNAPSHOT_KEYS:
            return _TooLarge()
        return tuple(sorted(
            ((str(k), snapshot(v, depth=depth + 1)) for k, v in items),
            key=lambda p: str(p[0]),
        ))
    if isinstance(value, (list, tuple)):
        seq = list(value)
        if len(seq) > _MAX_SNAPSHOT_ITEMS:
            return _TooLarge()
        return _ArrayMarker(snapshot(item, depth=depth + 1) for item in seq)
    return value


class _DepthExceeded:
    """Sentinel used inside snapshots to enforce depth limits."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "<depth>"


class _TooLarge:
    """Sentinel for oversized mappings/sequences."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "<too-large>"


# _ArrayMarker for unambiguous array vs object distinction in snapshots (N17)
class _ArrayMarker(tuple):
    """Tuple subclass marking a JSON array in the snapshot."""
    __slots__ = ()


def snapshot_body(body: Any) -> Any:
    """Snapshot the ``body`` parameter of a provider call (N12)."""
    if body is None:
        return None
    snap = snapshot(body)
    if isinstance(snap, (_DepthExceeded, _TooLarge)):
        from ..errors import ConnectorDenied
        raise ConnectorDenied("body_nested_too_deeply")
    return snap


def snapshot_payload(payload: Any) -> Any:
    """Snapshot the ``payload`` parameter of a provider entry point."""
    if payload is None:
        return None
    snap = snapshot(payload)
    if isinstance(snap, (_DepthExceeded, _TooLarge)):
        from ..errors import ConnectorDenied
        raise ConnectorDenied("payload_nested_too_deeply")
    return snap


# --- Credential snapshot ---------------------------------------------------

def credential_fingerprint(provider: str, token: Optional[str]) -> Optional[str]:
    """Stable SHA-256 of ``(provider, token)`` — never the token itself."""
    if not token:
        return None
    return hashlib.sha256(
        provider.encode("utf-8") + b"\x00" + token.encode("utf-8"),
    ).hexdigest()


def read_credential(token_env: Optional[str]) -> Optional[str]:
    """Read the credential **once** from the given env-var name.

    This is the single read point — the caller stores the result and
    reuses the exact value for fingerprint, verify and transmit (F07).
    """
    if not token_env:
        return None
    import os
    value = os.environ.get(token_env)
    return value.strip() if value else None


# --- Authorization-traffic budget -------------------------------------------

class AuthorizationBudget:
    """Bounded counter for all authorization traffic on one provider instance.

    Used by both providers to bound identity verification and ownership
    lookups independently of the grant's ``max_calls`` (N06).

    Thread-safe: every ``charge()`` is atomic.
    """

    def __init__(self, max_requests: int) -> None:
        self._max = max_requests
        self._count = 0
        self._lock = threading.Lock()

    def charge(self) -> Optional[str]:
        """Record one authorization request; returns a reason when exhausted."""
        with self._lock:
            self._count += 1
            if self._count > self._max:
                return "authorization_traffic_exhausted"
        return None

    @property
    def count(self) -> int:
        return self._count
