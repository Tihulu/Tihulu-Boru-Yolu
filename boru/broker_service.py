"""Authenticated local broker surface (P5 slice) — loopback only, bounded.

A tiny loopback TCP service where a local worker presents its identity (id +
secret, verified in constant time against the owner-created registry) and one
authorization request per connection. Nothing here executes an operation, and
nothing binds to a public address or starts automatically.

This is the *surface* the rest of P5 needs. It is not yet a security boundary:
host-level process authentication, OS confinement, transport encryption and an
independent security review remain HOLD, and the service refuses to start on a
non-loopback address.
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Any, Dict, Optional, Tuple

from .broker import Broker, OperationRequest
from .errors import PolicyViolation
from .workers import WorkerRegistry

MAX_REQUEST_BYTES = 8 * 1024
IDLE_TIMEOUT_SECONDS = 30.0
#: Bounded concurrency: one loopback surface never spawns unbounded threads.
MAX_CONCURRENT_CONNECTIONS = 4


class BrokerService:
    """Loopback, single-request-per-connection authorization service."""

    def __init__(self, broker: Broker, registry: WorkerRegistry, worker_id: str, secret: str,
                 host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in ("127.0.0.1", "::1"):
            raise PolicyViolation("broker service must bind loopback only")
        if secret is not None and (not isinstance(secret, str) or not secret):
            raise PolicyViolation("a worker secret is required")
        self.broker = broker
        self.registry = registry
        self.worker_id = worker_id
        self._secret = secret
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_CONNECTIONS)
        self._host = host
        self._socket = socket.socket(socket.AF_INET if ":" not in host else socket.AF_INET6,
                                     socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket.listen(4)
        self._socket.settimeout(0.5)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.host, self.port = self._socket.getsockname()[0], self._socket.getsockname()[1]

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> Tuple[str, int]:
        self._running = True

        def serve():
            while self._running:
                try:
                    connection, _ = self._socket.accept()
                except (socket.timeout, OSError):
                    continue
                threading.Thread(target=self._handle, args=(connection,), daemon=True).start()

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()
        return self.host, self.port

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        try:
            self._socket.close()
        except OSError:  # pragma: no cover - defensive cleanup
            pass

    # -- serving -------------------------------------------------------------
    def _handle(self, connection: socket.socket) -> None:
        if not self._slots.acquire(blocking=False):
            self._send(connection, {"decision": "deny", "reason": "service_busy"})
            try:
                connection.close()
            except OSError:
                pass
            return
        try:
            self._serve(connection)
        finally:
            self._slots.release()

    def _serve(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(IDLE_TIMEOUT_SECONDS)
            raw = self._read(connection)
            if raw is None:
                return
            try:
                request = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(connection, {"decision": "deny", "reason": "malformed_request"})
                return
            if not isinstance(request, dict):
                self._send(connection, {"decision": "deny", "reason": "malformed_request"})
                return
            self._send(connection, self._authorize(request))
        except (socket.timeout, OSError):
            pass
        finally:
            try:
                connection.close()
            except OSError:  # pragma: no cover - defensive cleanup
                pass

    def _authorize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        worker_id = payload.get("worker_id")
        secret = payload.get("secret")
        body = payload.get("request")
        if not self.registry.valid(self.worker_id, self._secret or ""):
            return {"decision": "deny", "reason": "worker_invalid"}
        if worker_id != self.worker_id or not isinstance(secret, str) \
                or not self.registry.valid(worker_id, secret):
            return {"decision": "deny", "reason": "worker_invalid"}
        if not isinstance(body, dict):
            return {"decision": "deny", "reason": "malformed_request"}
        try:
            target = body.get("target")
            level = body.get("level", "L0")
            if level not in ("L0", "L1"):
                return {"decision": "deny", "reason": "policy_requires_scoped_approved"}
            request = OperationRequest(
                operation=str(body.get("operation", "")),
                resource_alias=str(body.get("resource_alias", "")),
                requester=str(body.get("requester", "")),
                task_id=str(body.get("task_id", "")),
                worker=self.broker.worker.__class__(worker_id, scopes=tuple(self.broker.worker.scopes)),
                fields=tuple(str(f) for f in body.get("fields", ())),
                nonce=str(body.get("nonce", "")),
                grant_id=str(body.get("grant_id", "")),
                target=str(target) if isinstance(target, str) and target else None,
            )
        except (TypeError, ValueError):
            return {"decision": "deny", "reason": "malformed_request"}
        decision, receipt, reason = self.broker.authorize(
            request, level=level, requested_fields=request.fields)
        reply = {"decision": "allow" if decision == "allow" else "deny", "reason": reason}
        if receipt is not None:
            reply["receipt_id"] = receipt.receipt_id
            reply["operation"] = receipt.operation
            reply["expires_at"] = receipt.expires_at
            # The full signed receipt travels so the worker can verify it
            # locally; it carries identifiers only, never a path.
            reply["receipt"] = receipt.to_dict()
        return reply

    def _read(self, connection: socket.socket) -> Optional[bytes]:
        chunks: list = []
        total = 0
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                return b"".join(chunks) if chunks else None
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                return None
            chunks.append(chunk)
            if b"}" in chunk:
                return b"".join(chunks)

    @staticmethod
    def _send(connection: socket.socket, payload: Dict[str, Any]) -> None:
        try:
            connection.sendall(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        except (socket.timeout, OSError):  # pragma: no cover - client may close early
            pass


def ask(service: BrokerService, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    """Client helper used by tests and future local callers."""
    connection = socket.create_connection(("127.0.0.1", service.port), timeout=timeout)
    try:
        connection.sendall(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        raw = b""
        while b"}" not in raw:
            chunk = connection.recv(4096)
            if not chunk:
                break
            raw += chunk
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"decision": "deny", "reason": "invalid_response"}
    finally:
        try:
            connection.close()
        except OSError:  # pragma: no cover - defensive cleanup
            pass
