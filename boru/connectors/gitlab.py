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
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .scope import validate_request_scope

API_BASE = "https://gitlab.com"
MAX_PAGE = 100


class GitLabProvider(RepositoryProvider):
    """Official GitLab API v4 connector with grant-bound typed operations."""

    name = "gitlab"

    def __init__(self, *, base_url: str = API_BASE, token_env: Optional[str] = None,
                 transport=None, allow_http: bool = False) -> None:
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

    def capabilities(self) -> Tuple[Capability, ...]:
        return tuple(OPERATION_CAPABILITIES.values())

    def connection_state(self) -> str:
        if self.token_env and os.environ.get(self.token_env):
            return "authenticated"
        if self.token_env:
            return "configured"
        return "disconnected"

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
            raise ConnectorDenied(reason)
        scoped_payload = validate_request_scope(grant, operation, payload, body, method, path)
        path = self._path_for(operation, scoped_payload)
        method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(method, path, body or {})
        self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
        reason_event = "ok" if status < 300 else "http_" + str(status)
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                            "path": path, "status": status, "decision": "allow", "reason": reason_event})
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

    def _path_for(self, operation: str, payload: Mapping[str, Any]) -> str:
        project = str(payload.get("repository", "")).replace("/", "%2F")
        issue = str(payload.get("issue", ""))
        run_id = str(payload.get("run_id", ""))
        workflow = str(payload.get("workflow", ""))
        paths = {
            "list_repositories": "/api/v4/projects?per_page={}".format(MAX_PAGE),
            "read_file": "/api/v4/projects/{}/repository/files/{}?ref={}".format(
                project, payload.get("path", ""), payload.get("branch", "main")),
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

    def _exchange(self, method: str, path: str, body: Mapping[str, Any]) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(method, path, body)
        if not self.base_url.lower().startswith("https://"):
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
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            try:
                body_bytes = error.read()
            except Exception:  # pragma: no cover - defensive cleanup
                body_bytes = b""
            return error.code, body_bytes
        except urllib.error.URLError:
            raise ConnectorDenied("endpoint_unavailable")
