"""Boru Core local dashboard slice (P9 source slice).

A tiny loopback HTTP surface for the owner: task status, the four policy axes,
provider connection states, and an explicit review action.  It performs no
inference, holds no state of its own, and exposes nothing beyond loopback.

It is **not** an authorization surface.  Every restricted operation still goes
through Boru Core, and the dashboard cannot widen a policy axis, start a
provider call or release private data.
"""
from __future__ import annotations

import html
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from .errors import BoruError, StoreError
from .i18n import translate, summary_labels


def _summary(core) -> Dict[str, Any]:
    rows = core.store.by_state((
        "CREATED", "CLASSIFIED", "PLANNED", "QUEUED", "RUNNING", "VERIFYING", "REVIEW",
        "DONE", "FAILED", "CANCELLED", "HOLD",
    ))
    tasks = []
    for row in rows:
        record = core.store.get(row["task_id"]) or {}
        attempts = record.get("attempts") or []
        latest = attempts[-1] if attempts else {}
        tasks.append({
            "task_id": row["task_id"],
            "state": row["state"],
            "provider": latest.get("model_provider"),
            "model_id": latest.get("model_id"),
            "evidence_class": latest.get("evidence_class"),
        })
    return {
        "policy": core.policy.as_dict(),
        "providers": [
            {"kind": entry.kind, "models": [] if entry.kind == "mock" else list(entry.local_model_ids),
             "connection_state": core.provider_states().get(entry.api_key_env or "", "local") if entry.kind == "cloud" else "local"}
            for entry in core.config.providers
        ],
        "agents": {"max_logical": core.scheduler.max_agents},
        "tasks": tasks,
        "live_acceptance": "HOLD",
    }


class _Handler(BaseHTTPRequestHandler):
    core = None  # type: ignore[assignment]

    def log_message(self, *args):  # keep the console clean
        return

    def _json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render(self, status: HTTPStatus, title: str, payload: Dict[str, Any], language: str = "en") -> None:
        localized = summary_labels(language)
        localized = summary_labels(language)
        rows = "".join(
            "<tr><th>{}</th><td>{}</td></tr>".format(
                html.escape(localized.get(key, key)),
                html.escape(translate("hold") if value == "HOLD" else str(value)),
            )
            for key, value in payload.items()
        )
        body = (
            "<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            "<title>{title}</title></head><body><h1>{title}</h1>"
            "<table>{rows}</table><h2>{tasks}</h2><pre>{payload}</pre></body></html>"
        ).format(lang=html.escape(language), title=html.escape(translate(title, language)),
                 rows=rows, tasks=html.escape(localized["tasks"]),
                 payload=html.escape(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)))
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?lang="):
            language = "en"
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("lang="):
                        candidate = part[len("lang="):]
                        if candidate in ("en", "tr", "de"):
                            language = candidate
            self._render(HTTPStatus.OK, "title", _summary(self.core), language)
            return
        if self.path == "/status":
            self._json(HTTPStatus.OK, _summary(self.core))
            return
        if self.path.startswith("/task/"):
            task_id = self.path[len("/task/"):]
            try:
                self._json(HTTPStatus.OK, self.core.status(task_id))
            except StoreError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "unknown task"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/review":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                request = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed_request"})
                return
            task_id = request.get("task_id") if isinstance(request, dict) else None
            accept = request.get("accept") if isinstance(request, dict) else None
            if accept is not True:
                self._json(HTTPStatus.CONFLICT, {"error": "explicit_accept_required"})
                return
            if not isinstance(task_id, str) or not task_id.strip():
                self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed_request"})
                return
            try:
                self._json(HTTPStatus.OK, {"task_id": task_id,
                                           "state": self.core.review(task_id, accept=accept)})
            except StoreError as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": exc.kind})
            except BoruError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": exc.kind})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})


class BoruDashboard:
    """Loopback-only status surface for one Boru Core instance."""

    def __init__(self, core, host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("dashboard must bind loopback only")
        handler = type("BoruHandler", (_Handler,), {"core": core})
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.daemon_threads = True
        self._thread: Optional[threading.Thread] = None
        self.host, self.port = self._server.server_address[0], self._server.server_address[1]

    def start(self) -> Tuple[str, int]:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.host, self.port

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "BoruDashboard":
        self.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()
