"""Optional OpenCode adapter (P2 source slice) — official HTTP API, disabled by default.

OpenCode stays a **standalone** application: Boru never owns, configures or
stops it.  This adapter is an optional, explicitly configured client for a
loopback OpenCode server, used only for coding-agent tasks.  A real child
session ID and the returned model/provider identity are the only acceptable
evidence that a subagent ran; a `skill` invocation or a simulated reply is not
(sub)agent delegation (issue #3, ADR-0003).

Nothing here modifies OpenCode's global configuration, agents or providers, and
nothing here authorises Shell execution: restricted operations stay with the
trusted broker, which is not part of this slice.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from ..errors import ConnectorDenied


class OpenCodeAdapter:
    """Minimal, bounded client for a locally running OpenCode server."""

    def __init__(self, base_url: str, *, token_env: Optional[str] = None, allow_remote: bool = False) -> None:
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise ValueError("base_url is required")
        if any(c.isspace() for c in base_url) or "\\" in base_url or "@" in base_url.split("//", 1)[-1].split("/", 1)[0]:
            raise ValueError("malformed base_url")
        parts = urlsplit(base_url)
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("credentials, query and fragment are not permitted")
        if parts.scheme not in ("http", "https"):
            raise ValueError("only http and https are supported")
        host = parts.hostname
        if not host:
            raise ValueError("base_url host is required")
        if not allow_remote:
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                raise ValueError("OpenCode adapter accepts a numeric loopback endpoint only")
            if not address.is_loopback:
                raise ValueError("OpenCode adapter is loopback-only unless the owner allows a remote host")
        self._tls = parts.scheme == "https"
        self._host = host
        self._port = parts.port or (443 if self._tls else 80)
        self.token_env = token_env
        self.last_session_id: Optional[str] = None

    # -- official OpenCode endpoints -----------------------------------------
    def create_session(self, timeout: float = 10.0) -> str:
        status, raw = self._exchange("POST", "/api/session", {}, timeout)
        payload = self._json(status, raw)
        session = payload.get("id")
        if not isinstance(session, str) or not session.strip():
            raise ConnectorDenied("missing_session_id")
        self.last_session_id = session
        return session

    def prompt(self, session_id: str, text: str, *, timeout: float = 120.0) -> Dict[str, Any]:
        status, raw = self._exchange(
            "POST", "/api/session/{}/prompt".format(session_id),
            {"text": text[:32 * 1024]}, timeout)
        return self._json(status, raw)

    def get_session(self, session_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        status, raw = self._exchange("GET", "/api/session/{}".format(session_id), None, timeout)
        return self._json(status, raw)

    def interrupt(self, session_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        status, raw = self._exchange(
            "POST", "/api/session/{}/interrupt".format(session_id), {}, timeout)
        return self._json(status, raw)

    # -- bounded HTTP --------------------------------------------------------
    def _connect(self, remaining: float) -> http.client.HTTPConnection:
        if self._tls:
            return http.client.HTTPSConnection(self._host, self._port, timeout=remaining)
        return http.client.HTTPConnection(self._host, self._port, timeout=remaining)

    def _exchange(self, method: str, path: str, body: Optional[Mapping[str, Any]],
                  timeout: float) -> Tuple[int, bytes]:
        if self._tls is False and self._host not in ("127.0.0.1", "::1"):
            raise ConnectorDenied("insecure_endpoint")
        deadline = time.monotonic() + timeout
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token_env:
            import os

            token = os.environ.get(self.token_env)
            if token:
                headers["Authorization"] = "Bearer " + token.strip()
        conn = self._connect(max(deadline - time.monotonic(), 0.05))
        try:
            conn.request(method, path, body=json.dumps(body).encode("utf-8") if body is not None else None,
                         headers=headers)
            if conn.sock is not None:
                conn.sock.settimeout(max(deadline - time.monotonic(), 0.05))
            response = conn.getresponse()
            chunks: List[bytes] = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ConnectorDenied("timeout")
                if conn.sock is not None:
                    conn.sock.settimeout(max(remaining, 0.05))
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > 256 * 1024:
                    raise ConnectorDenied("response_too_large")
                chunks.append(chunk)
            return response.status, b"".join(chunks)
        except ConnectorDenied:
            raise
        except socket.timeout:
            raise ConnectorDenied("timeout")
        except (socket.error, OSError):
            raise ConnectorDenied("endpoint_unavailable")
        except http.client.HTTPException:
            raise ConnectorDenied("protocol_error")
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

    @staticmethod
    def _json(status: int, raw: bytes) -> Dict[str, Any]:
        if status in (401, 403):
            raise ConnectorDenied("unauthorized")
        if status == 404:
            raise ConnectorDenied("not_found")
        if status >= 500:
            raise ConnectorDenied("server_error")
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")
        if not isinstance(payload, dict):
            raise ConnectorDenied("invalid_response")
        return payload
