"""End-to-end local disclosure pipeline (P5 slice) — worker + broker + gate.

This wires the four local pieces together in one local-to-typed-result flow:

1. the **broker** authorizes a named operation on a declared resource alias for
   a worker that holds that scope, with a matching consent grant, and issues a
   **signed receipt**;
2. the **executor** verifies that receipt before touching anything, then
   acquires only the requested typed fields, alias-confined and read-only,
   resolving the target component-wise without following symlinks;
3. the **disclosure gate** decides what, if anything, may leave for a named
   recipient;
4. the **ledger** records every step with sanitized fields.

No cloud call is made here: this is the local half of the Privacy Bridge, and
its purpose is that a denial cannot leak and that a success carries only typed
fields.  The remote half (real recipient, L2 excerpt release, OS isolation)
remains HOLD pending independent security review.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional, Tuple

from .audit import RejectionLedger
from .authorization import AuthorizationReceipt, derive_key
from .broker import Broker, OperationRequest, ScopeAllowlist
from .consent import ConsentStore
from .errors import PolicyViolation
from .executor import LocalExecutor
from .privacy import FORBIDDEN_RESULT_KEYS, LEVEL_FIELDS, DisclosureGate, DisclosureRequest
from .workers import WorkerRegistry

#: The pipeline's own worker identity, scoped to the declared aliases only.
WORKER_ID = "boru-local-worker"


class DisclosurePipeline:
    """Local, fail-closed typed result flow for one recipient."""

    def __init__(self, *, worker: WorkerRegistry, consent: ConsentStore,
                 aliases: Mapping[str, str], ledger: Optional[RejectionLedger] = None,
                 receipt_ttl_seconds: float = 60.0,
                 service_endpoint: Optional[Tuple[str, int, str, str]] = None) -> None:
        self.workers = worker
        self.consent = consent
        self.ledger = ledger if ledger is not None else RejectionLedger()
        self.receipt_ttl_seconds = receipt_ttl_seconds
        self._executors: Dict[Tuple[str, ...], LocalExecutor] = {}
        # Owner-declared alias -> real host path. Never derived from a payload.
        self.aliases = dict(aliases or {})
        # (host, port, worker_id, secret) of an authenticated BrokerService.
        self.service_endpoint = service_endpoint

    def disclose(self, *, task_id: str, operation: str, alias: str, fields: Tuple[str, ...],
                 recipient: str, level: str = "L0", now: Optional[float] = None,
                 target: Optional[str] = None) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """Run the local flow and return ``(decision, typed_result, reason)``.

        When a loopback ``BrokerService`` endpoint is configured, the
        authorization step happens over that authenticated surface instead of
        in-process, so the identity handshake is part of the tested path.
        """
        if self.service_endpoint is not None:
            return self._disclose_over_service(task_id=task_id, operation=operation,
                                               alias=alias, fields=fields, recipient=recipient,
                                               level=level, now=now, target=target)
        return self._disclose_local(task_id=task_id, operation=operation, alias=alias,
                                    fields=fields, recipient=recipient, level=level,
                                    now=now, target=target)

    # -- in-process authorization -------------------------------------------
    def _disclose_local(self, *, task_id: str, operation: str, alias: str,
                        fields: Tuple[str, ...], recipient: str, level: str,
                        now: Optional[float] = None,
                        target: Optional[str] = None) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """Authorize in-process, then acquire and release."""
        record = self._live_worker(now=now)
        if record is None:
            return "deny", {}, "worker_unavailable"
        broker = self._broker(record)
        request = OperationRequest(operation=operation, resource_alias=alias, requester=recipient,
                                   task_id=task_id, worker=_identity(record), fields=fields,
                                   nonce="n-{}-{}".format(task_id, operation),
                                   grant_id="g-{}".format(task_id), target=target)
        decision, receipt, reason = broker.authorize(request, now=now, level=level,
                                                     requested_fields=fields)
        if decision != "allow" or receipt is None:
            self.ledger.record("broker", task_id, reason or "broker_denied", operation)
            return "deny", {}, reason or "broker_denied"
        return self._acquire_and_release(task_id=task_id, operation=operation, alias=alias,
                                         fields=fields, recipient=recipient, level=level,
                                         receipt=receipt, now=now)

    # -- loopback authorization ---------------------------------------------
    def _disclose_over_service(self, *, task_id: str, operation: str, alias: str,
                               fields: Tuple[str, ...], recipient: str, level: str,
                               now: Optional[float] = None,
                               target: Optional[str] = None) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """Authorize through the authenticated loopback service, then execute."""
        from .broker_service import ask

        host, port, worker_id, secret = self.service_endpoint
        reply = ask(self._service_client(host, port), {
            "worker_id": worker_id,
            "secret": secret,
            "request": {
                "operation": operation,
                "resource_alias": alias,
                "requester": recipient,
                "task_id": task_id,
                "worker": worker_id,
                "fields": list(fields),
                "nonce": "n-{}-{}".format(task_id, operation),
                "grant_id": "g-{}".format(task_id),
                "target": target or "",
                "level": level,
            },
        })
        if reply.get("decision") != "allow":
            reason = reply.get("reason") or "service_denied"
            self.ledger.record("broker", task_id, reason, operation)
            return "deny", {}, reason
        try:
            receipt = AuthorizationReceipt.from_dict(reply.get("receipt"))
        except PolicyViolation:
            self.ledger.record("broker", task_id, "receipt_unusable", operation)
            return "deny", {}, "receipt_unusable"
        return self._acquire_and_release(task_id=task_id, operation=operation, alias=alias,
                                         fields=fields, recipient=recipient, level=level,
                                         receipt=receipt, now=now)

    @staticmethod
    def _service_client(host: str, port: int):
        """A minimal view of a running BrokerService for the ask() helper."""
        class _Endpoint:
            def __init__(self, host: str, port: int) -> None:
                self.host, self.port = host, port

        return _Endpoint(host, port)

    # -- shared steps --------------------------------------------------------
    def _live_worker(self, *, now: Optional[float]):
        record = self.workers.get(WORKER_ID)
        if record is None or record.validate():
            return None
        secret = self.workers.secret_for(WORKER_ID)
        if not secret or not self.workers.valid(WORKER_ID, secret, now=now):
            return None
        return record

    def _broker(self, record) -> Broker:
        secret = self.workers.secret_for(WORKER_ID) or ""
        return Broker(worker=_identity(record), scopes=self._aliases(),
                      consent=self.consent, consent_recipient=record.worker_id,
                      receipt_ttl_seconds=self.receipt_ttl_seconds, audit=self.ledger,
                      registry=self.workers, worker_secret=secret)

    def _aliases(self) -> ScopeAllowlist:
        return ScopeAllowlist(self.aliases)

    def _acquire_and_release(self, *, task_id: str, operation: str, alias: str,
                             fields: Tuple[str, ...], recipient: str, level: str,
                             receipt: AuthorizationReceipt,
                             now: Optional[float] = None) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """Verify-bound acquisition, then the minimum-necessary release gate."""
        if level == "L2":
            # L2 needs SCOPED_APPROVED and a matching grant: refuse before
            # touching the resource, fail closed.
            self.ledger.record("disclosure", task_id, "policy_requires_scoped_approved", level)
            return "deny", {}, "policy_requires_scoped_approved"
        # The level decides what may leave before anything is acquired, so a
        # wider request never touches the resource at all.
        level_allowed = set(LEVEL_FIELDS.get(level, ()))
        if set(fields) & set(FORBIDDEN_RESULT_KEYS):
            self.ledger.record("disclosure", task_id, "private_field_refused", level)
            return "deny", {}, "private_field_refused"
        unknown = [name for name in fields if name not in level_allowed]
        if unknown:
            self.ledger.record("disclosure", task_id, "field_not_allowed_for_level", level)
            return "deny", {}, "field_not_allowed_for_level"
        record = self.workers.get(WORKER_ID)
        if record is None or record.validate():
            return "deny", {}, "worker_unavailable"
        secret = self.workers.secret_for(WORKER_ID) or ""
        executor = self._executor(secret)
        try:
            acquisition = executor.acquire(receipt, fields=fields, now=_now(now))
        except PolicyViolation:
            self.ledger.record("executor", task_id, "acquisition_refused", operation)
            return "deny", {}, "acquisition_refused"
        gate = DisclosureGate("MINIMUM_NECESSARY", audit=self.ledger)
        gate_decision, payload, gate_reason = gate.release(
            DisclosureRequest(task_id=task_id, recipient=recipient, level=level,
                              fields=fields, payload=dict(acquisition.fields)),
            consent=self.consent, now=_now(now))
        if gate_decision.value != "release":
            self.ledger.record("disclosure", task_id, gate_reason or "disclosure_refused", level)
            return "deny", {}, gate_reason or "disclosure_refused"
        self.ledger.record("disclosure", task_id, "released", level)
        return "release", payload, ""

    def _executor(self, secret: str) -> LocalExecutor:
        key = tuple(sorted(self.aliases))
        executor = self._executors.get(key)
        if executor is None:
            executor = LocalExecutor(self._aliases(), authorization_key=derive_key(secret))
            self._executors[key] = executor
        return executor


def _identity(record):
    from .broker import WorkerIdentity

    return WorkerIdentity(record.worker_id, scopes=record.scopes)


def _now(now: Optional[float]) -> float:
    return now if now is not None else time.time()
