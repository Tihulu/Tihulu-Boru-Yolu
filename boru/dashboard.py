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
from typing import Any, Dict, List, Optional, Tuple

from .errors import BoruError, ConfigurationError, StoreError
from .i18n import translate, summary_labels

#: A local owner surface is still a surface: the request body, the task path
#: segment and the concurrent connections are bounded.
MAX_BODY_BYTES = 64 * 1024
MAX_PATH_SEGMENT = 128
MAX_CONNECTIONS = 4
#: The page is fully self-contained: no external resource is loaded at all.
CONTENT_SECURITY_POLICY = "default-src 'none'; form-action 'none'; base-uri 'none'"


AXIS_KEYS = (
    ("optimization_mode", "axis_routing"),
    ("inference_scope", "axis_inference"),
    ("execution_profile", "axis_execution"),
    ("disclosure_policy", "axis_disclosure"),
)


def _axis_rows(payload: Dict[str, Any], localized: Dict[str, str]) -> str:
    """Render the four policy axes as separate, labelled rows."""
    policy = payload.get("policy") or {}
    rows = []
    for key, label in AXIS_KEYS:
        value = str(policy.get(key, "UNKNOWN"))
        rows.append("<dt>{}</dt><dd>{}</dd>".format(html.escape(localized.get(label, label)),
                                                   html.escape(value)))
    return "".join(rows)


def core_rows(core, state: str) -> List[Dict[str, Any]]:
    return [row for row in core.store.by_state((state,)) if row["state"] == state]


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
    audit = None
    _slots = None  # bounded-connection semaphore, attached by BoruDashboard

    def handle(self) -> None:
        """Bound concurrent connections before any request is processed."""
        slots = type(self)._slots
        if slots is None or slots.acquire(blocking=False):
            try:
                super().handle()
            finally:
                if slots is not None:
                    slots.release()
            return
        # Refuse without a slot.  The whole request is drained first: closing a
        # socket with unread bytes would reset the connection, and the owner's
        # client would see a reset instead of the refusal it should read.
        try:
            drained = 0
            while drained < MAX_BODY_BYTES:
                line = self.rfile.readline(65537)
                drained += len(line)
                if not line or line in (b"\r\n", b"\n"):
                    break
            # parse_request never ran, so the attributes the response writer
            # reads are set here rather than left to fail.
            self.requestline = ""
            self.request_version = "HTTP/1.0"
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "dashboard_busy"})
        except Exception:  # pragma: no cover - client may close early
            pass

    def log_message(self, *args):  # keep the console clean
        return

    def _headers(self, content_type: str, length: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _render(self, status: HTTPStatus, title: str, payload: Dict[str, Any], language: str = "en") -> None:
        localized = summary_labels(language)
        payload_json = html.escape(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
        audit_rows = self.audit.recent(8) if self.audit is not None else []
        axes = _axis_rows(payload, localized)
        audit_line = "".join(
            "<li>{} / {}</li>".format(html.escape(str(row.get("category"))), html.escape(str(row.get("reason"))))
            for row in audit_rows
        )
        rows = "".join(
            "<tr><th>{}</th><td>{}</td></tr>".format(
                html.escape(localized.get(key, key)),
                html.escape(translate("hold") if value == "HOLD" else str(value)),
            )
            for key, value in payload.items()
        )
        body = (
            "<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            "<title>{title}</title></head><body>"
            "<h1>{title}</h1>"
            "<section aria-labelledby=\"policy-heading\">"
            "<h2 id=\"policy-heading\">{policy}</h2>"
            "<table><caption>{policy}</caption><tbody>{rows}</tbody></table>"
            "</section>"
            "<section aria-labelledby=\"axes-heading\">"
            "<h2 id=\"axes-heading\">{axes_title}</h2><dl>{axes}</dl>"
            "</section>"
            "<section aria-labelledby=\"tasks-heading\">"
            "<h2 id=\"tasks-heading\">{tasks}</h2><pre>{payload}</pre>"
            "</section>"
            "<section aria-labelledby=\"audit-heading\">"
            "<h2 id=\"audit-heading\">{audit_title}</h2><ul>{audit}</ul>"
            "</section>"
            "<form action=\"/review\" method=\"post\" aria-labelledby=\"review-heading\">"
            "<h2 id=\"review-heading\">{review}</h2>"
            "<label for=\"review-task\">{review_task}</label>"
            "<input id=\"review-task\" name=\"task_id\" type=\"text\" required>"
            "<button type=\"submit\" name=\"accept\" value=\"true\">{accept}</button>"
            "</form>"
            "</body></html>"
        ).format(lang=html.escape(language), title=html.escape(translate(title, language)),
                 policy=html.escape(localized["policy"]), rows=rows, axes=axes,
                 tasks=html.escape(localized["tasks"]), payload=payload_json,
                 axes_title=html.escape(localized["policy"]),
                 audit_title=html.escape(localized["audit"]),
                 audit=audit_line or "<li>no rejections recorded</li>",
                 review=html.escape(localized["review"]),
                 review_task=html.escape(translate("review", language)),
                 accept=html.escape(translate("accept", language)))
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
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
        if self.path == "/status" or self.path.startswith("/status?lang="):
            self._json(HTTPStatus.OK, _summary(self.core))
            return
        if self.path == "/audit":
            rows = self.audit.recent(32) if self.audit is not None else []
            self._json(HTTPStatus.OK, {"rejections": rows, "live_acceptance": "HOLD"})
            return
        if self.path == "/queue":
            review = core_rows(self.core, "REVIEW")
            self._json(HTTPStatus.OK, {"awaiting_review": review, "live_acceptance": "HOLD"})
            return
        if self.path.startswith("/task/"):
            task_id = self.path[len("/task/"):].split("?", 1)[0]
            if not task_id or len(task_id) > MAX_PATH_SEGMENT or "/" in task_id:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed_request"})
                return
            try:
                self._json(HTTPStatus.OK, self.core.status(task_id))
            except StoreError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "unknown task"})
            except ConfigurationError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed_request"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/review":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed_request"})
                return
            if length < 0 or length > MAX_BODY_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_too_large"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                request = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
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

    def __init__(self, core, host: str = "127.0.0.1", port: int = 0, audit=None) -> None:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("dashboard must bind loopback only")
        # A loopback surface is still bounded: beyond the connection limit the
        # handler refuses instead of spawning unbounded threads.
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        handler = type("BoruHandler", (_Handler,), {"core": core, "audit": audit,
                                                   "_slots": self._slots})
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
