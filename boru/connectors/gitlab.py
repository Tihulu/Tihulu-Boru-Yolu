"""Official GitLab REST connector (P8 source slice) — typed, grant-bound.

GitLab.com and owner-allowlisted self-managed instances. Same rules as the
GitHub connector: a denied operation produces no outbound request, tokens only
enter through an environment-variable name, and a token is identity only.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .scope import check_call, check_dispatch_body

API_BASE = "https://gitlab.com"
MAX_PAGE = 100
#: An error body is diagnostic, never a payload: keep only a bounded prefix.
MAX_ERROR_BODY_BYTES = 4 * 1024


def _bounded_read(stream, limit: int) -> bytes:
    """Read at most ``limit`` bytes from an HTTP error body."""
    if not hasattr(stream, "read"):
        return b""
    try:
        return stream.read(limit)
    except Exception:  # pragma: no cover - defensive cleanup
        return b""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect: a connector call must never be silently followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise ConnectorDenied("redirects_not_followed")


class GitLabProvider(RepositoryProvider):
    """Official GitLab API v4 connector with grant-bound typed operations."""

    name = "gitlab"

    def __init__(self, *, base_url: str = API_BASE, token_env: Optional[str] = None,
                 transport=None, allow_http: bool = False, audit=None) -> None:
        # allow_http is an owner opt-in for pinned loopback test endpoints only.
        self.allow_http_endpoints = allow_http
        if token_env is not None and (not isinstance(token_env, str) or not token_env.strip()
                                      or len(token_env) > 64):
            raise PolicyViolation("token_env must be a bounded environment variable name")
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise PolicyViolation("base_url must be a bounded non-empty string")
        if not base_url.lower().startswith("https://") and not allow_http:
            raise PolicyViolation("GitLab API requires https")
        self.base_url = base_url.rstrip("/")
        self.token_env = token_env
        self._transport = transport
        self._audit: List[Dict[str, Any]] = []
        self._calls: Dict[str, int] = {}
        self._ledger = audit
        # The verified identity: a fingerprint of the token that was checked,
        # never the account string.  A rotated token has a different
        # fingerprint, so a stale identity cannot authorize it.
        self._identity_fingerprint: Optional[str] = None

    def capabilities(self) -> Tuple[Capability, ...]:
        return tuple(OPERATION_CAPABILITIES.values())

    def connection_state(self) -> str:
        if self.token_env and os.environ.get(self.token_env):
            return "authenticated"
        if self.token_env:
            return "configured"
        return "disconnected"

    def verify_identity(self, expected_account: str, timeout: float = 10.0) -> Tuple[bool, str]:
        """Verify the account behind the token against the grant's account."""
        if not self.token_env or not os.environ.get(self.token_env):
            return False, "configured"
        if not expected_account or not isinstance(expected_account, str):
            return False, "grant_account_invalid"
        try:
            status, raw = self._account_request(timeout)
        except ConnectorDenied as exc:
            return False, str(exc)
        if status != 200:
            return False, "identity_endpoint_refused"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, "invalid_response"
        if not isinstance(data, dict):
            return False, "invalid_response"
        username = data.get("username")
        if not isinstance(username, str) or not username.strip():
            return False, "identity_endpoint_refused"
        if username != expected_account:
            return False, "identity_mismatch"
        return True, "authenticated"

    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    def check(self, grant: Grant, operation: str) -> Tuple[bool, str]:
        if grant.validate():
            return False, "grant_invalid"
        return grant.permits(operation, time.time(), self._calls.get(grant.grant_id, 0))

    def call(self, grant: Grant, operation: str, payload: Optional[Mapping[str, Any]] = None,
             *, method: Optional[str] = None, path: str = "",
             body: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        if operation not in OPERATION_CAPABILITIES:
            raise ConnectorDenied("unknown_operation")
        allowed, reason = self.check(grant, operation)
        if not allowed:
            self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                                "decision": "deny", "reason": reason})
            if self._ledger is not None:
                self._ledger.record("connector", grant.grant_id, reason, operation)
            raise ConnectorDenied(reason)
        if path:
            raise ConnectorDenied("path_override_refused")
        try:
            # The slots returned here are the only values used to build the
            # request: what was checked is what is sent.
            slots = check_call(grant, operation, payload or {}, method=method, path=path,
                               default_method=self._MUTATING.get(operation, "GET"))
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise
        # A dispatch body is validated before any transport is constructed.
        if operation == "dispatch_workflow":
            try:
                check_dispatch_body(grant, body or {})
            except ConnectorDenied as exc:
                self._deny(grant, operation, str(exc))
                raise
        # A token proves an identity, never write or Shell authorization.
        self._require_account_identity(grant)
        path = self._path_for(operation, slots)
        if method is None:
            method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(method, path, body or {})
        self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
        reason_event = "ok" if status < 300 else "http_" + str(status)
        # A URL path never enters the audit event: the operation and status
        # describe the call without naming a repository route.
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                            "path_kind": "official_endpoint", "status": status,
                            "decision": "allow", "reason": reason_event})
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")

    #: mutating methods for the official v4 endpoints
    _MUTATING = {
        "create_issue": "POST", "comment_issue": "POST", "update_issue": "PUT",
        "create_branch": "POST", "put_file": "POST", "create_pull": "POST",
        "review_pull": "POST", "merge_pull": "PUT", "dispatch_workflow": "POST",
        "rerun_workflow": "POST", "cancel_run": "POST", "configure_workflow": "PUT",
        "create_release": "POST",
    }

    # -- identity -------------------------------------------------------------
    def _deny(self, grant: Grant, operation: str, reason: str) -> None:
        """Record a denial without any repository route."""
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id,
                            "operation": operation, "decision": "deny", "reason": reason})
        if self._ledger is not None:
            self._ledger.record("connector", grant.grant_id, reason, operation)

    def _token_value(self) -> Optional[str]:
        """The configured credential, read at request time and never stored."""
        if not self.token_env:
            return None
        value = os.environ.get(self.token_env)
        return value.strip() if value else None

    @staticmethod
    def _token_fingerprint(provider: str, token: Optional[str]) -> Optional[str]:
        """A stable fingerprint of (provider, token), never the token itself."""
        if not token:
            return None
        import hashlib

        return hashlib.sha256(provider.encode("utf-8") + b"\x00" + token.encode("utf-8")).hexdigest()

    def _require_account_identity(self, grant: Grant) -> None:
        """Verify the account behind the token once per provider instance."""
        account = getattr(grant, "account", None)
        if not self.token_env or not isinstance(account, str) or not account.strip():
            return
        fingerprint = self._token_fingerprint(self.name, self._token_value())
        if fingerprint is None or fingerprint == self._identity_fingerprint:
            return
        verified, reason = self.verify_identity(account)
        if not verified:
            raise ConnectorDenied(reason)
        # Only a token that was actually checked is remembered.
        self._identity_fingerprint = fingerprint

    # -- official endpoint paths ---------------------------------------------
    def _path_for(self, operation: str, payload: Mapping[str, Any]) -> str:
        project = self._project(payload)
        issue = str(payload.get("issue", ""))
        run_id = str(payload.get("run_id", ""))
        workflow = str(payload.get("workflow", ""))
        # The reference already passed the grant check: the query string uses
        # exactly that validated value and never a default branch.
        reference = str(payload.get("reference", payload.get("branch", "")))
        paths = {
            "list_repositories": "/api/v4/projects?per_page={}".format(MAX_PAGE),
            "read_file": "/api/v4/projects/{}/repository/files/{}?ref={}".format(
                project, payload.get("path", ""), reference),
            "list_branches": "/api/v4/projects/{}/repository/branches".format(project),
            "get_commit": "/api/v4/projects/{}/repository/commits/{}".format(project, payload.get("sha", "")),
            "list_issues": "/api/v4/projects/{}/issues?per_page={}".format(project, MAX_PAGE),
            "create_issue": "/api/v4/projects/{}/issues".format(project),
            "comment_issue": "/api/v4/projects/{}/issues/{}/notes".format(project, issue),
            "update_issue": "/api/v4/projects/{}/issues/{}".format(project, issue),
            "get_pull": "/api/v4/projects/{}/merge_requests/{}".format(project, issue),
            "create_branch": "/api/v4/projects/{}/repository/branches".format(project),
            "put_file": "/api/v4/projects/{}/repository/files/{}".format(project, payload.get("path", "")),
            "create_pull": "/api/v4/projects/{}/merge_requests".format(project),
            "review_pull": "/api/v4/projects/{}/merge_requests/{}/notes".format(project, issue),
            "merge_pull": "/api/v4/projects/{}/merge_requests/{}/merge".format(project, issue),
            "list_workflows": "/api/v4/projects/{}/pipelines".format(project),
            "dispatch_workflow": "/api/v4/projects/{}/pipeline".format(project),
            "rerun_workflow": "/api/v4/projects/{}/pipeline_schedules/{}/play".format(project, workflow),
            "cancel_run": "/api/v4/projects/{}/pipelines/{}/cancel".format(project, run_id),
            "get_run": "/api/v4/projects/{}/pipelines/{}".format(project, run_id),
            "get_run_logs": "/api/v4/projects/{}/pipelines/{}/jobs".format(project, run_id),
            "get_artifacts": "/api/v4/projects/{}/pipelines/{}/bridges".format(project, run_id),
            "configure_workflow": "/api/v4/projects/{}/pipeline_schedules/{}".format(project, workflow),
            "create_release": "/api/v4/projects/{}/releases".format(project),
        }
        return paths.get(operation, "")

    def _account_request(self, timeout: float) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport("GET", "/api/v4/user", {})
        opener = urllib.request.build_opener(_NoRedirect)
        headers = {"Accept": "application/json", "User-Agent": "tihulu-boru-core"}
        token = os.environ.get(self.token_env) if self.token_env else None
        if token:
            headers["PRIVATE-TOKEN"] = token.strip()
        request = urllib.request.Request(self.base_url + "/api/v4/user", method="GET",
                                          headers=headers)
        try:
            with opener.open(request, timeout=timeout) as response:
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                if content_type and content_type not in ("application/json", "text/plain"):
                    raise ConnectorDenied("unexpected_content_type")
                return response.status, response.read(512 * 1024)
        except ConnectorDenied:
            raise
        except urllib.error.HTTPError as error:
            body_bytes = _bounded_read(error, MAX_ERROR_BODY_BYTES)
            return error.code, body_bytes
        except urllib.error.URLError:
            raise ConnectorDenied("endpoint_unavailable")

    @staticmethod
    def _project(payload) -> str:
        from .scope import RepositoryRef

        return RepositoryRef.parse(str(payload.get("repository", ""))).percent_encoded()

    def _exchange(self, method: str, path: str, body: Mapping[str, Any]) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(method, path, body)
        if not self.base_url.lower().startswith("https://") and not self.allow_http_endpoints:
            raise ConnectorDenied("insecure_endpoint")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "User-Agent": "tihulu-boru-core"}
        token = os.environ.get(self.token_env) if self.token_env else None
        if token:
            headers["PRIVATE-TOKEN"] = token.strip()
        request = urllib.request.Request(self.base_url + path, method=method,
                                         data=json.dumps(body).encode("utf-8") if body else None,
                                         headers=headers)
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=30) as response:
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                if content_type and content_type not in ("application/json", "text/plain"):
                    raise ConnectorDenied("unexpected_content_type")
                raw = response.read(512 * 1024)
                return response.status, raw
        except ConnectorDenied:
            raise
        except urllib.error.HTTPError as error:
            try:
                body_bytes = _bounded_read(error, MAX_ERROR_BODY_BYTES)
            except Exception:  # pragma: no cover - defensive cleanup
                body_bytes = b""
            return error.code, body_bytes
        except urllib.error.URLError:
            raise ConnectorDenied("endpoint_unavailable")
