"""Official GitHub REST connector (P8 source slice) — typed, grant-bound.

This connector never decides rights for itself: every call is matched against
an owner-issued `Grant`, and a denied operation produces **no outbound
request**. Tokens are only ever read from an environment variable named by
configuration, and no token, body or private payload appears in errors or
audit events (issue #9).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .scope import check_call

API_BASE = "https://api.github.com"


class GitHubProvider(RepositoryProvider):
    """Official GitHub API connector with grant-bound typed operations."""

    name = "github"

    def __init__(self, *, token_env: Optional[str] = None, base_url: str = API_BASE,
                 transport=None, allow_http: bool = False, audit=None) -> None:
        if token_env is not None and (not isinstance(token_env, str) or not token_env.strip() or len(token_env) > 64):
            raise PolicyViolation("token_env must be a bounded environment variable name")
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise PolicyViolation("base_url must be a bounded non-empty string")
        if not base_url.lower().startswith("https://") and not allow_http:
            raise PolicyViolation("GitHub API requires https")
        self.token_env = token_env
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._audit: List[Dict[str, Any]] = []
        self._calls: Dict[str, int] = {}
        self._ledger = audit

    # -- identity ------------------------------------------------------------
    def capabilities(self) -> Tuple[Capability, ...]:
        return tuple(OPERATION_CAPABILITIES.values())

    def connection_state(self) -> str:
        """Honest state: a token is identity, not write authorization."""
        if self.token_env and os.environ.get(self.token_env):
            return "authenticated"
        if self.token_env:
            return "configured"
        return "disconnected"

    # -- grants --------------------------------------------------------------

    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    def check(self, grant: Grant, operation: str) -> Tuple[bool, str]:
        problems = grant.validate()
        if problems:
            return False, "grant_invalid"
        return grant.permits(operation, time.time(), self._calls.get(grant.grant_id, 0))

    #: Operations that change remote state use a mutating method by default.
    _MUTATING = {
        "create_issue": "POST", "comment_issue": "POST", "update_issue": "PATCH",
        "create_branch": "POST", "put_file": "PUT", "create_pull": "POST",
        "review_pull": "POST", "merge_pull": "PUT", "dispatch_workflow": "POST",
        "rerun_workflow": "POST", "cancel_run": "POST", "configure_workflow": "PUT",
        "create_release": "POST",
    }

    def call(self, grant: Grant, operation: str, payload: Optional[Mapping[str, Any]] = None,
             *, method: Optional[str] = None, path: str = "", body: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Perform one typed, grant-checked operation or raise ConnectorDenied."""
        if operation not in OPERATION_CAPABILITIES:
            raise ConnectorDenied("unknown_operation")
        allowed, reason = self.check(grant, operation)
        if not allowed:
            self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                                "decision": "deny", "reason": reason})
            if self._ledger is not None:
                self._ledger.record("connector", grant.grant_id, reason, operation)
            raise ConnectorDenied(reason)
        # The requested repository/reference must be the granted one, and no raw
        # method/path override may reach the official endpoint (issue #15).
        if path:
            raise ConnectorDenied("path_override_refused")
        try:
            check_call(grant, operation, payload or {}, method=method, path=path,
                       default_method=self._MUTATING.get(operation, "GET"))
        except ConnectorDenied as exc:
            self._audit.append({"at": int(time.time()), "grant": grant.grant_id,
                                "operation": operation, "decision": "deny",
                                "reason": str(exc)})
            if self._ledger is not None:
                self._ledger.record("connector", grant.grant_id, str(exc), operation)
            raise
        path = self._path_for(operation, payload or {})
        if method is None:
            method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(operation, method, path, body or {})
        self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
        event_reason = "ok" if status < 300 else "http_" + str(status)
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                            "path": path, "status": status, "decision": "allow", "reason": event_reason})
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            raise ConnectorDenied("invalid_response")

    # -- request paths (official endpoints only) -----------------------------
    def _path_for(self, operation: str, payload: Mapping[str, Any]) -> str:
        repository = str(payload.get("repository", ""))
        issue = str(payload.get("issue", ""))
        run_id = str(payload.get("run_id", ""))
        workflow = str(payload.get("workflow", ""))
        branch = str(payload.get("branch", ""))
        paths = {
            "list_repositories": "/user/repos",
            "read_file": "/repos/{}/contents/{}".format(repository, payload.get("path", "")),
            "list_branches": "/repos/{}/branches".format(repository),
            "get_commit": "/repos/{}/commits/{}".format(repository, payload.get("sha", "")),
            "list_issues": "/repos/{}/issues".format(repository),
            "create_issue": "/repos/{}/issues".format(repository),
            "comment_issue": "/repos/{}/issues/{}/comments".format(repository, issue),
            "update_issue": "/repos/{}/issues/{}".format(repository, issue),
            "get_pull": "/repos/{}/pulls/{}".format(repository, issue),
            "create_branch": "/repos/{}/git/refs".format(repository),
            "put_file": "/repos/{}/contents/{}".format(repository, payload.get("path", "")),
            "create_pull": "/repos/{}/pulls".format(repository),
            "review_pull": "/repos/{}/pulls/{}/reviews".format(repository, issue),
            "merge_pull": "/repos/{}/pulls/{}/merge".format(repository, issue),
            "list_workflows": "/repos/{}/actions/workflows".format(repository),
            "dispatch_workflow": "/repos/{}/actions/workflows/{}/dispatches".format(repository, workflow),
            "rerun_workflow": "/repos/{}/actions/runs/{}/rerun".format(repository, run_id),
            "cancel_run": "/repos/{}/actions/runs/{}/cancel".format(repository, run_id),
            "get_run": "/repos/{}/actions/runs/{}".format(repository, run_id),
            "get_run_logs": "/repos/{}/actions/runs/{}/logs".format(repository, run_id),
            "get_artifacts": "/repos/{}/actions/runs/{}/artifacts".format(repository, run_id),
            "configure_workflow": "/repos/{}/actions/workflows/{}".format(repository, workflow),
            "create_release": "/repos/{}/releases".format(repository),
        }
        if branch and operation in ("read_file", "list_branches"):
            return paths[operation] + "?ref={}".format(branch)
        return paths.get(operation, "")

    # -- bounded HTTP --------------------------------------------------------
    def _exchange(self, operation: str, method: str, path: str, body: Mapping[str, Any]) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(method, path, body)
        if not self.base_url.lower().startswith("https://"):
            raise ConnectorDenied("insecure_endpoint")
        headers = {"Accept": "application/vnd.github+json", "Content-Type": "application/json",
                   "User-Agent": "tihulu-boru-core"}
        token = os.environ.get(self.token_env) if self.token_env else None
        if token:
            headers["Authorization"] = "Bearer " + token.strip()
        request = urllib.request.Request(self.base_url + path, method=method,
                                         data=json.dumps(body).encode("utf-8") if body else None,
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            body_bytes = error.read() if hasattr(error, "read") else b""
            return error.code, body_bytes
        except urllib.error.URLError:
            raise ConnectorDenied("endpoint_unavailable")

    # -- helpers used by tests and callers -----------------------------------
    def read_only_check(self, operations: Sequence[str]) -> List[str]:
        """Return the operations a read-only profile must refuse (a guard test)."""
        from .base import WRITE_OPERATIONS

        return sorted(set(operations) & WRITE_OPERATIONS)


def read_only_denies(provider: GitHubProvider, grant: Grant) -> List[str]:
    """Return every operation the given grant refuses, without any request."""
    refused = []
    for operation in OPERATION_CAPABILITIES:
        allowed, _ = provider.check(grant, operation)
        if not allowed:
            refused.append(operation)
    return refused
