"""End-to-end local disclosure pipeline (P5 slice) — worker + broker + gate.

This wires the four local pieces together in one local-to-typed-result flow:

1. the **broker** authorizes a named operation on a declared resource alias for
   a worker that holds that scope, with a matching consent grant;
2. the **executor** acquires only the requested typed fields, alias-confined
   and read-only;
3. the **disclosure gate** decides what, if anything, may leave for a named
   recipient;
4. the **ledger** records every step with sanitized fields.

No cloud call is made here: this is the local half of the Privacy Bridge, and
its purpose is that a denial cannot leak and that a success carries only typed
fields.  The remote half (real recipient, L2 excerpt release, OS isolation)
remains HOLD pending independent security review.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .audit import RejectionLedger
from .broker import Broker, OperationRequest
from .consent import ConsentStore
from .errors import PolicyViolation
from .executor import LocalExecutor
from .privacy import DisclosureGate, DisclosureRequest
from .workers import WorkerRegistry

#: The pipeline's own worker identity, scoped to the declared aliases only.
WORKER_ID = "boru-local-worker"


class DisclosurePipeline:
    """Local, fail-closed typed result flow for one recipient."""

    def __init__(self, *, worker: WorkerRegistry, consent: ConsentStore,
                 ledger: Optional[RejectionLedger] = None,
                 receipt_ttl_seconds: float = 60.0) -> None:
        self.workers = worker
        self.consent = consent
        self.ledger = ledger if ledger is not None else RejectionLedger()
        self.receipt_ttl_seconds = receipt_ttl_seconds
        self._executors: Dict[Tuple[str, ...], LocalExecutor] = {}

    def disclose(self, *, task_id: str, operation: str, alias: str, fields: Tuple[str, ...],
                 recipient: str, level: str = "L0", now: Optional[float] = None) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """Run the local flow and return ``(decision, typed_result, reason)``."""
        record = self.workers.get(WORKER_ID)
        if record is None or record.validate():
            return "deny", {}, "worker_unavailable"
        if not self.workers.valid(WORKER_ID, self.workers.secret_for(WORKER_ID) or "", now=now):
            return "deny", {}, "worker_unavailable"
        if not self.workers.valid(WORKER_ID, self.workers.secret_for(WORKER_ID) or "", now=now):
            return "deny", {}, "worker_unavailable"
        from .broker import ScopeAllowlist

        aliases = self._aliases_for(record)
        broker = Broker(worker=_identity(record), scopes=aliases, consent=self.consent,
                        receipt_ttl_seconds=self.receipt_ttl_seconds, audit=self.ledger,
                        consent_recipient=record.worker_id)
        request = OperationRequest(operation=operation, resource_alias=alias, requester=recipient,
                                   task_id=task_id, worker=_identity(record), fields=fields,
                                   nonce="n-{}-{}".format(task_id, operation), grant_id="g-{}".format(task_id))
        decision, receipt, reason = broker.authorize(request, now=now)
        if decision != "allow" or receipt is None:
            self.ledger.record("broker", task_id, reason or "broker_denied", operation)
            return "deny", {}, reason or "broker_denied"
        gate = DisclosureGate("MINIMUM_NECESSARY", audit=self.ledger)
        if level == "L2":
            # L2 needs SCOPED_APPROVED and a matching grant: refuse before
            # touching the resource, fail closed.
            self.ledger.record("disclosure", task_id, "policy_requires_scoped_approved", level)
            return "deny", {}, "policy_requires_scoped_approved"
        executor = self._executor(aliases)
        try:
            acquisition = executor.acquire(receipt, fields=fields, now=_now(now))
        except PolicyViolation as exc:
            self.ledger.record("executor", task_id, "acquisition_refused", operation)
            return "deny", {}, "acquisition_refused"
        request_out = DisclosureRequest(task_id=task_id, recipient=recipient, level=level,
                                        fields=fields, payload=dict(acquisition.fields))
        gate_decision, payload, gate_reason = gate.release(request_out, consent=self.consent,
                                                           now=_now(now))
        if gate_decision.value != "release":
            self.ledger.record("disclosure", task_id, gate_reason or "disclosure_refused", level)
            return "deny", {}, gate_reason or "disclosure_refused"
        self.ledger.record("disclosure", task_id, "released", level)
        return "release", payload, ""

    # -- helpers -------------------------------------------------------------
    def _aliases_for(self, record) -> "ScopeAllowlist":
        from .broker import ScopeAllowlist

        aliases = {scope: scope for scope in record.scopes}
        return ScopeAllowlist(aliases)

    def _executor(self, aliases) -> LocalExecutor:
        key = tuple(sorted(aliases.aliases))
        executor = self._executors.get(key)
        if executor is None:
            executor = LocalExecutor(aliases)
            self._executors[key] = executor
        return executor


def _identity(record):
    from .broker import WorkerIdentity

    return WorkerIdentity(record.worker_id, scopes=record.scopes)


def _now(now: Optional[float]) -> float:
    return now if now is not None else __import__("time").time()
