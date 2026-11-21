"""Cloud-Shell grant contract (P6 source slice) — decisions only, never execution.

This implements the *authorization* half of `docs/SECURITY_MODES.md`: the
grant a local authority issues so a cloud model may direct an allowlisted
operation inside a broker-controlled project sandbox.  It is deliberately a
decision layer:

* no process, container, mount or network is created here;
* the sandbox itself is not implemented, so any "would run" answer is a
  decision, not an execution;
* P6 remains **blocked** until the P5 broker passes live acceptance and the
  owner explicitly consents.

Every denial reason from the design is enforced, and a decision is recorded in
the rejection ledger.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .audit import RejectionLedger
from .errors import PolicyViolation

POLICY_REVISION = 1
MAX_RESOURCE_ALIASES = 8
MAX_OPERATION_TYPES = 8
MAX_CALLS = 64
MAX_MINUTES = 240

#: Operation types a cloud-directed sandbox may request. Host-level Shell is
#: deliberately absent.
SANDBOX_OPERATIONS: Tuple[str, ...] = (
    "read_file_alias",
    "list_dir_alias",
    "probe_path_alias",
    "run_synthetic_command",
)


@dataclass(frozen=True)
class SandboxGrant:
    """One owner-issued, recipient-bound, revocable sandbox grant."""

    grant_id: str
    owner_id: str
    recipient_provider: str
    recipient_model: str
    task_id: str
    sandbox_id: str
    operation_types: Tuple[str, ...]
    resource_aliases: Tuple[str, ...]
    field_disclosures: Tuple[str, ...] = ()
    issued_at: float = 0.0
    expires_at: float = 0.0
    max_calls: int = 0
    nonce: str = ""
    revoked: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        for name, limit in (("grant_id", 128), ("owner_id", 128), ("recipient_provider", 64),
                            ("recipient_model", 128), ("task_id", 128), ("sandbox_id", 128),
                            ("nonce", 64)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(name + " must be a bounded non-empty string")
        if not isinstance(self.operation_types, tuple) or not self.operation_types:
            errors.append("operation_types must be a non-empty tuple")
        elif len(self.operation_types) > MAX_OPERATION_TYPES or any(
                op not in SANDBOX_OPERATIONS for op in self.operation_types):
            errors.append("operation_types must be allowlisted sandbox operations")
        if not isinstance(self.resource_aliases, tuple) or not self.resource_aliases:
            errors.append("resource_aliases must be a non-empty tuple")
        elif len(self.resource_aliases) > MAX_RESOURCE_ALIASES or any(
                not isinstance(a, str) or not a.strip() or len(a) > 64
                or any(part in ("", ".", "..") for part in a.split("/")) for a in self.resource_aliases):
            errors.append("resource_aliases must be bounded, non-traversing alias names")
        if not isinstance(self.field_disclosures, tuple) or len(self.field_disclosures) > MAX_RESOURCE_ALIASES:
            errors.append("field_disclosures must be a bounded tuple")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(name + " must be a finite timestamp")
        if isinstance(self.issued_at, (int, float)) and isinstance(self.expires_at, (int, float)) \
                and self.expires_at <= self.issued_at:
            errors.append("expires_at must follow issued_at")
        if self.issued_at and self.expires_at:
            lifetime_minutes = (self.expires_at - self.issued_at) / 60.0
            if lifetime_minutes > MAX_MINUTES:
                errors.append("grant lifetime is capped at {} minutes".format(MAX_MINUTES))
        if isinstance(self.max_calls, bool) or not isinstance(self.max_calls, int) \
                or not 1 <= self.max_calls <= MAX_CALLS:
            errors.append("max_calls must be 1..{}".format(MAX_CALLS))
        if not isinstance(self.revoked, bool):
            errors.append("revoked must be a boolean")
        return errors


class SandboxBroker:
    """Fail-closed sandbox authorization for cloud-directed operations.

    A decision here is an authorization decision only. The sandbox itself is
    not implemented in this slice, so a successful authorization still cannot
    execute anything, and P6 stays blocked until P5 passes live acceptance and
    the owner explicitly consents.
    """

    def __init__(self, *, worker_scopes: Sequence[str] = (), ledger: Optional[RejectionLedger] = None,
                 policy_revision: int = POLICY_REVISION) -> None:
        if policy_revision != POLICY_REVISION:
            raise PolicyViolation("unsupported policy revision")
        self.policy_revision = policy_revision
        self.worker_scopes = tuple(worker_scopes)
        self.ledger = ledger if ledger is not None else RejectionLedger()
        self._calls: Dict[str, int] = {}
        self._nonces: Set[str] = set()
        self._revoked: Set[str] = set()

    def revoke(self, grant_id: str) -> None:
        self._revoked.add(_bounded(grant_id, 128, "grant_id"))

    def authorize(self, grant: SandboxGrant, *, operation: str, alias: str,
                  worker_scope: str, now: Optional[float] = None, sandbox_available: bool = False,
                  field_requested: Optional[str] = None) -> Tuple[bool, str]:
        """Return ``(allowed, reason)``; no operation is ever executed here."""
        errors = grant.validate()
        if errors:
            self._record(grant, "grant_invalid", operation)
            return False, "grant_invalid"
        stamp = time.time() if now is None else float(now)
        if grant.revoked or grant.grant_id in self._revoked:
            self._record(grant, "grant_revoked", operation)
            return False, "grant_revoked"
        if stamp >= grant.expires_at:
            self._record(grant, "grant_expired", operation)
            return False, "grant_expired"
        if operation not in grant.operation_types:
            self._record(grant, "operation_not_granted", operation)
            return False, "operation_not_granted"
        if alias not in grant.resource_aliases:
            self._record(grant, "resource_not_granted", operation)
            return False, "resource_not_granted"
        if field_requested is not None and field_requested not in grant.field_disclosures:
            self._record(grant, "field_not_granted", operation)
            return False, "field_not_granted"
        if worker_scope not in self.worker_scopes:
            self._record(grant, "worker_scope", operation)
            return False, "worker_scope"
        if self._calls.get(grant.grant_id, 0) >= grant.max_calls:
            self._record(grant, "grant_exhausted", operation)
            return False, "grant_exhausted"
        if grant.nonce in self._nonces:
            self._record(grant, "nonce_replayed", operation)
            return False, "nonce_replayed"
        if not sandbox_available:
            # The sandbox is not implemented in this slice, so there is no
            # environment in which the operation could run.
            self._record(grant, "sandbox_unavailable", operation)
            return False, "sandbox_unavailable"
        self._nonces.add(grant.nonce)
        self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
        return True, ""

    def _record(self, grant: SandboxGrant, reason: str, operation: str) -> None:
        self.ledger.record("policy", grant.task_id or grant.grant_id, reason, operation)

    def calls_used(self, grant_id: str) -> int:
        return self._calls.get(_bounded(grant_id, 128, "grant_id"), 0)


def _bounded(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PolicyViolation(label + " must be a bounded non-empty string")
    return value
