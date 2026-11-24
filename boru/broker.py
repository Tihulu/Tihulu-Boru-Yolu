"""Boru Core operation authorization (P5).

The broker answers one question: may this authenticated worker, holding this
consent grant, perform this operation on this declared resource alias for this
task, now?  Every denial is fail-closed and recorded in the local ledger.

Invariants enforced here (with tests in tests/test_broker.py):
* the worker identity must be authenticated against an owner-created registry
  when one is configured; an asserted identity (no registry) is an in-process
  owner decision, never a remote caller's claim;
* the consent grant must bind the recipient, task, operation, **resource
  alias**, **field** and **level**, and must be unexpired, unrevoked and
  unused - and the recipient is named explicitly, never omitted;
* the resource alias must be declared in the allowlist, and the alias is a
  name, never a path;
* every issued receipt is signed with an authorization key the worker also
  holds, so a tampered or borrowed receipt cannot be executed;
* a nonce is consumed once, and anti-replay state is bounded;
* the audit subject is a bounded, path-free identifier.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Set, Tuple

from .authorization import AuthorizationReceipt  # re-exported for callers
from .audit import RejectionLedger, safe_identifier
from .authorization import AuthorizationReceipt, derive_key, sign
from .errors import PolicyViolation

MAX_ALIAS = 64
MAX_NONCES = 4096
TOKEN_PREFIX = "r-"

#: A receipt names a resource only by this opaque form.
_TOKEN_RE = re.compile("^r-[0-9a-f]{16}$")

#: The typed local operations a worker may be asked to perform. Anything else
#: (a shell, a network write, a mutation) is refused before any other check.
ALLOWED_OPERATIONS: frozenset = frozenset({
    "probe_path_alias",
    "read_file_alias",
    "list_dir_alias",
    "run_synthetic_command",
})


def file_name(value: Any) -> str:
    """A single-segment file name inside an alias: never a path.

    ``.`` and ``..`` name the alias root and its parent, not an entry, so a
    receipt can never be issued for them.
    """
    name = safe_identifier(value, 64, "file name")
    if name in (".", ".."):
        raise PolicyViolation("file name must name an entry, not a directory reference")
    return name


def valid_resource_path(path: Any) -> bool:
    """An owner-declared resource path: absolute, normalized, no symlink.

    Every component of the path is checked, so an intermediate symlink (a
    bridge directory pointing outside the resource) is refused as firmly as a
    dangling final one.
    """
    if not isinstance(path, str) or not path.strip() or len(path) > 1024:
        return False
    if not os.path.isabs(path):
        return False
    normalized = os.path.normpath(path)
    if normalized != path:
        return False
    if ".." in normalized.split(os.sep):
        return False
    prefix = normalized
    while True:
        if os.path.islink(prefix):
            return False
        parent = os.path.dirname(prefix)
        if parent == prefix:
            return True
        prefix = parent


def resource_alias(value: Any) -> str:
    """A resource alias is an owner-declared name or an absolute path.

    A name is a bounded, path-free token. A path is accepted only when the
    owner declared it in the resource allowlist; either way the alias is never
    extended by a payload, and a receipt carries an opaque token, never the
    path itself.
    """
    if isinstance(value, str) and valid_resource_path(value):
        return value
    return safe_identifier(value, MAX_ALIAS, "resource alias")


@dataclass(frozen=True)
class WorkerIdentity:
    """A local worker attestation presented with a request."""

    worker_id: str
    scopes: Tuple[str, ...] = ()

    def validate(self) -> List[str]:
        errors: List[str] = []
        try:
            safe_identifier(self.worker_id, 64, "worker_id")
        except PolicyViolation as exc:
            errors.append(str(exc))
        try:
            for scope in self.scopes:
                resource_alias(scope)
        except PolicyViolation as exc:
            errors.append(str(exc))
        if len(set(self.scopes)) != len(self.scopes):
            errors.append("duplicate worker scopes")
        return errors


@dataclass(frozen=True)
class ScopeAllowlist:
    """Owner-declared resource aliases mapped to real host paths.

    The mapping is owner-provided configuration; no model, task payload or
    adapter can extend it.  A receipt carries the alias, never the path.
    """

    aliases: Mapping[str, str]

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.aliases, Mapping) or not self.aliases:
            return ["at least one resource alias is required"]
        for alias, path in self.aliases.items():
            try:
                resource_alias(alias)
            except PolicyViolation as exc:
                errors.append(str(exc))
                continue
            if not valid_resource_path(path):
                errors.append("alias must map to an absolute, normalized, symlink-free path")
        return errors

    def permits(self, alias: Any) -> bool:
        try:
            return resource_alias(alias) in self.aliases
        except PolicyViolation:
            return False

    def path_for(self, alias: Any) -> str:
        """Resolve an alias to its real path (never exposed to a caller)."""
        name = resource_alias(alias)
        path = self.aliases.get(name)
        if not path:
            raise PolicyViolation("resource alias is not declared")
        return path

    def token_for(self, alias: Any) -> str:
        """An opaque, stable token for a declared alias (never the path).

        Both the broker and the worker derive the same token from the shared
        owner-declared allowlist, so a receipt can name a resource without
        disclosing where it lives.
        """
        path = self.path_for(alias)
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
        return TOKEN_PREFIX + digest[:16]

    def alias_for_token(self, token: Any) -> Optional[str]:
        """Return the declared alias a token names, or ``None``."""
        if not isinstance(token, str) or not _TOKEN_RE.match(token):
            return None
        for alias in self.aliases:
            if hmac.compare_digest(self.token_for(alias), token):
                return alias
        return None


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
    target: Optional[str] = None

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.operation, str) or not self.operation.strip() or len(self.operation) > 64:
            errors.append("operation must be a bounded non-empty string")
        if not isinstance(self.fields, tuple) or len(self.fields) > 8:
            errors.append("fields must be a bounded tuple")
        for name in ("requester", "task_id", "nonce", "grant_id"):
            try:
                safe_identifier(getattr(self, name), 128, name)
            except PolicyViolation as exc:
                errors.append(str(exc))
        try:
            resource_alias(self.resource_alias)
        except PolicyViolation as exc:
            errors.append(str(exc))
        if self.target is not None:
            try:
                file_name(self.target)
            except PolicyViolation as exc:
                errors.append(str(exc))
        errors.extend(self.worker.validate())
        return errors


class Broker:
    """Fail-open never: fail-closed authorization decisions, with receipts."""

    POLICY_REVISION = 1

    def __init__(self, *, worker: Optional[WorkerIdentity], scopes: ScopeAllowlist, consent,
                 consent_recipient: Optional[str] = None,
                 worker_registry=None, worker_secret: Optional[str] = None,
                 receipt_ttl_seconds: float = 60.0, audit=None,
                 registry=None, authorization_key: Optional[bytes] = None) -> None:
        if consent is None:
            raise PolicyViolation("a consent store is required to authorize")
        if scopes.validate():
            raise PolicyViolation("resource allowlist is invalid")
        if receipt_ttl_seconds is None or isinstance(receipt_ttl_seconds, bool) \
                or not isinstance(receipt_ttl_seconds, (int, float)) \
                or not math.isfinite(receipt_ttl_seconds) or not 1.0 <= receipt_ttl_seconds <= 3600:
            raise PolicyViolation("receipt_ttl_seconds must be 1..3600")
        # The consent recipient is the owner-configured subject every grant is
        # bound to.  A broker that does not know it cannot authorize: without
        # one the store would be asked to match a grant whose recipient the
        # broker cannot name, which is the omission F03 describes.
        if not isinstance(consent_recipient, str) or not consent_recipient.strip():
            raise PolicyViolation("an explicit consent recipient is required")
        safe_identifier(consent_recipient, 64, "consent recipient")
        self.receipt_ttl_seconds = float(receipt_ttl_seconds)
        self._nonces: Set[str] = set()
        self._nonce_order: List[str] = []
        self.audit = audit if audit is not None else RejectionLedger()
        self.scopes = scopes
        self.consent = consent
        self.registry = registry if registry is not None else worker_registry
        self.consent_recipient = consent_recipient
        self.worker = worker
        self.key = self._resolve_key(authorization_key, worker_secret)

    def _resolve_key(self, authorization_key: Optional[bytes],
                     worker_secret: Optional[str]) -> bytes:
        """The receipt key: explicit, worker-secret derived, or process-local."""
        if authorization_key is not None:
            if not isinstance(authorization_key, (bytes, bytearray)) or len(authorization_key) != 32:
                raise PolicyViolation("authorization key must be 256 bits")
            return bytes(authorization_key)
        if worker_secret is not None:
            if not isinstance(worker_secret, str) or len(worker_secret) != 64:
                raise PolicyViolation("a worker secret is required")
            if self.registry is not None:
                # The secret must match the registry before it can key receipts.
                if not self.worker or not self.registry.valid(self.worker.worker_id, worker_secret):
                    raise PolicyViolation("the worker secret does not match the registry")
            return derive_key(worker_secret)
        if self.registry is not None and self.worker is not None:
            secret = self.registry.secret_for(self.worker.worker_id)
            if secret:
                return derive_key(secret)
        # No registry: an in-process owner decision.  The key is random and
        # never leaves this process, so receipts stay tamper-proof.
        return secrets.token_bytes(32)

    # -- decisions -----------------------------------------------------------
    def authorize(self, request: OperationRequest, *, now: Optional[float] = None,
                  level: str = "L0", requested_fields: Sequence[str] = ()) -> Tuple[str, Optional[AuthorizationReceipt], str]:
        """Return ``(decision, receipt_or_none, reason)``."""
        reason = self._check(request, now=now, level=level, requested_fields=requested_fields)
        if reason:
            self.audit.record("broker", self._subject(request), reason, self._detail(request))
            return "deny", None, reason
        stamp = time.time() if now is None else float(now)
        receipt = self._issue(request, stamp, fields=requested_fields)
        if receipt is None:  # pragma: no cover - defensive
            return "deny", None, "receipt_unavailable"
        return "allow", receipt, ""

    def _check(self, request: OperationRequest, *, now: Optional[float], level: str,
               requested_fields: Sequence[str]) -> str:
        alias = request.resource_alias
        if not isinstance(alias, str) or not alias.strip() or len(alias) > MAX_ALIAS:
            return "malformed_request"
        try:
            resource_alias(alias)
        except PolicyViolation:
            return "resource_not_declared"
        if not isinstance(request.operation, str) or not request.operation.strip() \
                or len(request.operation) > 64:
            return "malformed_request"
        if request.operation not in ALLOWED_OPERATIONS:
            return "operation_not_allowed"
        if not isinstance(request.fields, tuple) or len(request.fields) > 8 \
                or any(not isinstance(f, str) or not f.strip() or len(f) > 64 for f in request.fields):
            return "fields_invalid"
        for name in ("requester", "task_id", "nonce", "grant_id"):
            try:
                safe_identifier(getattr(request, name), 128, name)
            except PolicyViolation:
                return "malformed_request"
        if request.target is not None:
            try:
                file_name(request.target)
            except PolicyViolation:
                return "malformed_request"
        if request.worker.validate():
            return "worker_invalid"
        # Identity must be authenticated, not merely asserted.  Without a
        # registry the broker was built for one in-process worker identity:
        # a request may not widen that identity, only present it.
        if self.registry is None:
            if self.worker is None:
                return "worker_invalid"
            if request.worker.worker_id != self.worker.worker_id:
                return "worker_invalid"
            if not set(request.worker.scopes) <= set(self.worker.scopes):
                return "worker_scope"
        if self.registry is not None:
            record = self.registry.get(request.worker.worker_id)
            if record is None or record.revoked or record.validate():
                return "worker_invalid"
            secret = self.registry.secret_for(request.worker.worker_id)
            if not secret or self.key != derive_key(secret):
                return "worker_invalid"
            if not self.registry.valid(request.worker.worker_id, secret, now=now):
                return "worker_invalid"
            # The permitted scopes come from the authenticated registry record,
            # never from the request: a worker may not widen its own scopes by
            # declaring them, and a request that names more than it holds - or
            # less than it needs for this alias - is refused, not ignored.
            scopes = record.scopes
            if set(request.worker.scopes) != set(scopes):
                return "worker_scope"
        else:
            scopes = request.worker.scopes
        if request.nonce in self._nonces:
            return "nonce_replayed"
        if request.resource_alias not in scopes:
            return "worker_scope"
        if not self.scopes.permits(request.resource_alias):
            return "resource_not_declared"
        # Consent binds recipient, task, operation, alias, field and level.
        # The recipient is the configured consent subject, never a value the
        # request itself can choose, and it is always present: the broker
        # refuses to construct without one.
        try:
            allowed = self.consent.check(
                grant_id=request.grant_id, recipient=self.consent_recipient,
                task_id=request.task_id, field_name=request.operation,
                alias=request.resource_alias, level=level, nonce=request.nonce, now=now)
        except PolicyViolation:
            return "grant_invalid"
        if not allowed:
            return "grant_invalid"
        self._remember(request.nonce)
        return ""

    def _issue(self, request: OperationRequest, stamp: float,
               fields: Sequence[str]) -> Optional[AuthorizationReceipt]:
        expiry = stamp + self.receipt_ttl_seconds
        allowed = tuple(fields)
        # The signature covers exactly what the receipt carries: the opaque
        # resource token, never the alias or its path.
        token = self.scopes.token_for(request.resource_alias)
        tag = sign(self.key, task_id=request.task_id, operation=request.operation,
                   alias=token, worker_id=request.worker.worker_id,
                   grant_id=request.grant_id, nonce=request.nonce, expires_at=expiry,
                   fields=allowed, target=request.target or "")
        return AuthorizationReceipt(
            receipt_id="br-{}-{}".format(request.task_id, request.operation),
            operation=request.operation, resource_alias=token,
            task_id=request.task_id, worker_id=request.worker.worker_id,
            grant_id=request.grant_id, issued_at=stamp, expires_at=expiry,
            nonce=request.nonce, policy_revision=self.POLICY_REVISION,
            decision="allow", allowed_fields=allowed, target=request.target or "",
            authentication_tag=tag)

    def _remember(self, nonce: str) -> None:
        self._nonces.add(nonce)
        self._nonce_order.append(nonce)
        if len(self._nonce_order) > MAX_NONCES:
            drop = self._nonce_order.pop(0)
            self._nonces.discard(drop)

    @staticmethod
    def _subject(request: OperationRequest) -> str:
        try:
            return safe_identifier(request.task_id, 128, "task_id")
        except PolicyViolation:
            return "unidentified_task"

    @staticmethod
    def _detail(request: OperationRequest) -> str:
        """A ledger-safe detail kind; a malformed operation is still recorded."""
        try:
            return safe_identifier(request.operation, 64, "operation")
        except PolicyViolation:
            return "unspecified"
