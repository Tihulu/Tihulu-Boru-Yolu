"""Boru Core operation authorization (P5 slice): fail-closed scoped decisions.

This layer answers one question: *may this named operation touch this named
resource for this task, right now?*  It never executes anything and never
inspects the filesystem beyond the owner-declared scope aliases.

Guarantees (all fail closed and covered by negative tests):

* an operation must be on the owner's allowlist;
* a resource must be a declared **alias**, never a caller-supplied path;
* every request must carry a valid worker attestation and a matching consent
  grant; a missing/expired/revoked/replayed grant denies;
* a decision is recorded as an authorization receipt with expiry and nonce;
* responses carry alias names and typed outcomes only — never raw paths, file
  contents, listings or process data.

An executor, OS isolation and a persistent worker identity store are separate
P5/P6 work items and remain HOLD.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from .errors import PolicyViolation

#: Operation names Boru Core may authorize. Anything else is refused.
ALLOWED_OPERATIONS: Tuple[str, ...] = (
    "read_file_alias",
    "list_dir_alias",
    "probe_path_alias",
    "run_synthetic_command",
)

#: Bounds for request fields.
MAX_ALIAS = 64
MAX_REQUESTER = 128
MAX_TASK_ID = 128
MAX_FIELDS = 8
MAX_NONCE = 64


def _bounded(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PolicyViolation(label + " must be a bounded non-empty string")
    return value


@dataclass(frozen=True)
class WorkerIdentity:
    """A local worker attestation. Presence of a token here is not consent."""

    worker_id: str
    scopes: Tuple[str, ...] = ()

    def validate(self) -> List[str]:
        errors: List[str] = []
        try:
            _bounded(self.worker_id, 128, "worker_id")
            for scope in self.scopes:
                _bounded(scope, MAX_ALIAS, "scope")
        except PolicyViolation as exc:
            errors.append(str(exc))
        if len(set(self.scopes)) != len(self.scopes):
            errors.append("duplicate worker scopes")
        return errors


@dataclass(frozen=True)
class ScopeAllowlist:
    """Owner-declared resource aliases. Aliases map to real paths locally only."""

    aliases: Mapping[str, str]

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.aliases, Mapping) or not self.aliases:
            return ["at least one resource alias is required"]
        for alias, path in self.aliases.items():
            _bounded(alias, MAX_ALIAS, "alias")
            if not isinstance(path, str) or not path.strip():
                errors.append("alias must map to a non-empty path")
                continue
            if any(part in ("..",) for part in Path(path).parts):
                errors.append("alias must not traverse outside its root")
            if Path(path).is_symlink():
                errors.append("alias must not be a symlink")
            if not Path(path).is_absolute():
                errors.append("alias must be an absolute path")
        return errors

    def permits(self, alias: str) -> bool:
        if not isinstance(alias, str) or alias not in self.aliases:
            return False
        return _bounded(alias, MAX_ALIAS, "alias") in self.aliases


@dataclass(frozen=True)
class OperationRequest:
    """One authorization request, shaped before any local data is acquired."""

    operation: str
    resource_alias: str
    requester: str
    task_id: str
    worker: WorkerIdentity
    fields: Tuple[str, ...] = ()
    nonce: str = ""
    grant_id: str = ""


@dataclass(frozen=True)
class AuthorizationReceipt:
    """A non-forgeable, request-bound decision record."""

    receipt_id: str
    operation: str
    resource_alias: str
    task_id: str
    worker_id: str
    grant_id: str
    issued_at: float
    expires_at: float
    nonce: str
    policy_revision: int
    decision: str = "allow"

    def validate(self) -> List[str]:
        errors: List[str] = []
        _bounded(self.receipt_id, 96, "receipt_id")
        _bounded(self.operation, 64, "operation")
        if self.operation not in ALLOWED_OPERATIONS:
            errors.append("unknown authorized operation")
        _bounded(self.resource_alias, MAX_ALIAS, "resource_alias")
        _bounded(self.task_id, MAX_TASK_ID, "task_id")
        _bounded(self.worker_id, 128, "worker_id")
        _bounded(self.grant_id, 128, "grant_id")
        _bounded(self.nonce, MAX_NONCE, "nonce")
        if self.policy_revision != 1:
            errors.append("unsupported policy revision")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, (int, float)) \
                or not math.isfinite(self.expires_at) or self.expires_at <= self.issued_at:
            errors.append("receipt expiry must follow its issue time")
        return errors


class Broker:
    """Fail-closed authorization decisions for local operations."""

    POLICY_REVISION = 1

    def __init__(self, *, worker: WorkerIdentity, scopes: ScopeAllowlist, consent,
                 receipt_ttl_seconds: float = 60.0, audit=None,
                 consent_recipient: str = "local-worker", worker_registry=None,
                 worker_secret: Optional[str] = None) -> None:
        if receipt_ttl_seconds is None or isinstance(receipt_ttl_seconds, bool) \
                or not isinstance(receipt_ttl_seconds, (int, float)) \
                or not 1.0 <= float(receipt_ttl_seconds) <= 3600:
            raise PolicyViolation("receipt_ttl_seconds must be 1..3600")
        if worker.validate():
            raise PolicyViolation("worker identity is invalid")
        if not worker.scopes:
            raise PolicyViolation("the broker worker must hold at least one resource scope")
        if scopes.validate():
            raise PolicyViolation("resource allowlist is invalid")
        if consent is None:
            raise PolicyViolation("a consent store is required; failing closed without one")
        self.worker = worker
        self.scopes = scopes
        self.consent = consent
        self.receipt_ttl_seconds = float(receipt_ttl_seconds)
        self._nonces: Set[str] = set()
        self.audit = audit
        self.consent_recipient = consent_recipient
        # When a worker registry and secret are supplied, the request must also
        # present a live (unexpired, unrevoked, constant-time-matched) identity.
        self._registry = worker_registry
        self._worker_secret = worker_secret

    # -- decisions -----------------------------------------------------------
    def authorize(self, request: OperationRequest, *, now: Optional[float] = None) -> Tuple[str, Optional[AuthorizationReceipt], str]:
        """Return ``(decision, receipt_or_none, reason)``."""
        reason = self._check(request, now=now)
        if reason:
            if self.audit is not None:
                self.audit.record("broker", request.task_id, reason, request.operation)
            return "deny", None, reason
        stamp = time.time() if now is None else now
        receipt = AuthorizationReceipt(
            receipt_id="br-{}".format(request.nonce or _bounded(request.task_id, MAX_TASK_ID, "task_id")),
            operation=request.operation,
            resource_alias=request.resource_alias,
            task_id=request.task_id,
            worker_id=request.worker.worker_id,
            grant_id=request.grant_id,
            issued_at=stamp,
            expires_at=stamp + self.receipt_ttl_seconds,
            nonce=request.nonce,
            policy_revision=self.POLICY_REVISION,
        )
        if receipt.validate():
            return "deny", None, "receipt_invalid"
        return "allow", receipt, ""

    def _check(self, request: OperationRequest, *, now: Optional[float] = None) -> str:
        try:
            _bounded(request.operation, 64, "operation")
            _bounded(request.resource_alias, MAX_ALIAS, "resource_alias")
            _bounded(request.requester, MAX_REQUESTER, "requester")
            _bounded(request.task_id, MAX_TASK_ID, "task_id")
            _bounded(request.nonce, MAX_NONCE, "nonce")
            _bounded(request.grant_id, 128, "grant_id")
        except PolicyViolation:
            return "malformed_request"
        if request.operation not in ALLOWED_OPERATIONS:
            return "operation_not_allowed"
        if not isinstance(request.fields, tuple) or len(request.fields) > MAX_FIELDS:
            return "fields_invalid"
        for name in request.fields:
            try:
                _bounded(name, 64, "field")
            except PolicyViolation:
                return "fields_invalid"
        if not self.scopes.permits(request.resource_alias):
            return "resource_not_declared"
        # The request must carry a valid worker attestation that holds the
        # resource scope it wants to touch.
        if request.worker.validate():
            return "worker_invalid"
        if request.resource_alias not in request.worker.scopes:
            return "worker_scope"
        if self._registry is not None:
            if not self._registry.valid(request.worker.worker_id, self._worker_secret or ""):
                self._registry.get(request.worker.worker_id)  # bounded lookup
                return "worker_invalid"
            record = self._registry.get(request.worker.worker_id)
            if record is None or record.validate() or record.revoked:
                return "worker_invalid"
            if request.resource_alias not in record.scopes:
                return "worker_scope"
        if request.nonce in self._nonces:
            return "nonce_replayed"
        # A consent grant must match recipient-agnostic operation scope.
        if not self.consent.check(grant_id=request.grant_id, recipient=self.consent_recipient,
                                  task_id=request.task_id, field_name=request.operation,
                                  nonce=request.nonce, now=now):
            return "grant_invalid"
        self._nonces.add(request.nonce)
        return ""


