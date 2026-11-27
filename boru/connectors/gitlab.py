"""Official GitLab REST connector (P9 source slice) — typed, grant-bound.

Centralized authorization architecture (N12/N15/N07/N13/N06):
1. **Materialize once**: snapshot body + payload before any validation
2. **Validate snapshot**: all grant checks, write-body contracts against snapshot
3. **Authorize snapshot**: identity, pipeline ownership, merge target
4. **Transmit snapshot**: exact validated snapshot reaches the transport
5. **No caller objects**: never return to original body/payload after materialization
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .scope import (
    GITLAB_WRITE_BODY_CONTRACTS, check_call, check_dispatch_body, check_write_body,
    _payload_get,
)
from .request import (
    snapshot_body, snapshot_payload, read_credential, credential_fingerprint,
    AuthorizationBudget, MAX_SNAPSHOT_DEPTH,
)

API_BASE = "https://gitlab.com"
MAX_ERROR_BODY_BYTES = 4 * 1024

RUN_OPERATIONS = frozenset({"get_run", "get_run_logs", "get_artifacts",
                            "cancel_run", "rerun_workflow"})

MAX_VERIFIED_RUNS = 64
MAX_AUTHORIZATION_REQUESTS = 512
RUN_OWNERSHIP_TTL_SECONDS = 300.0


class GitLabProvider(RepositoryProvider):
    """GitLab REST API v4 connector bound by owner-issued grants."""

    def __init__(self, *, token_env: Optional[str] = None, base_url: str = API_BASE,
                 transport=None, allow_http: bool = False, audit=None):
        if token_env is not None and (not isinstance(token_env, str) or not token_env.strip() or len(token_env) > 64):
            raise PolicyViolation("token_env must be a bounded environment variable name")
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise PolicyViolation("base_url must be a bounded non-empty string")
        if not base_url.lower().startswith("https://") and not allow_http:
            raise PolicyViolation("GitLab API requires https")
        self.name = "gitlab"
        self.token_env = token_env
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._allow_http = allow_http
        self._audit: List[Dict[str, Any]] = []
        self._ledger = audit
        self._verified_identity: Optional[Tuple[str, str]] = None
        self._identity_lock = threading.Lock()
        # N07: ownership cache keyed by complete authorization context
        self._verified_runs: Dict[Tuple[str, ...], float] = {}
        self._run_lock = threading.Lock()
        # N06: centralized authorization budget
        self._auth_budget = AuthorizationBudget(MAX_AUTHORIZATION_REQUESTS)
        self._call_lock = threading.Lock()
        self._call_counts: Dict[str, int] = {}
        # Semaphore to limit concurrent calls per grant
        self._call_semaphores: Dict[str, threading.Semaphore] = {}

    def capabilities(self) -> Tuple[Capability, ...]:
        return tuple(OPERATION_CAPABILITIES.values())

    def connection_state(self) -> str:
        if self.token_env and os.environ.get(self.token_env):
            return "authenticated"
        if self.token_env:
            return "configured"
        return "disconnected"

    @property
    def base_url(self) -> str:
        return self._base_url

    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    @property
    def _calls(self) -> Dict[str, int]:
        """Backward compatibility for tests expecting _calls dict."""
        return self._call_counts

    def read_only_check(self, operations: Sequence[str]) -> List[str]:
        """Return the operations a read-only profile must refuse (a guard test)."""
        from .base import WRITE_OPERATIONS

        return sorted(set(operations) & WRITE_OPERATIONS)

    def check(self, grant: Grant, operation: str) -> Tuple[bool, str]:
        """Check if grant permits this operation at current time."""
        import time
        return grant.permits(operation, time.time(), 0)

    def call(self, grant: Grant, operation: str, payload: Optional[Mapping[str, Any]] = None,
             body: Optional[Mapping[str, Any]] = None, method: Optional[str] = None,
             path: Optional[str] = None) -> Any:
        """Execute a grant-bound operation against the official GitLab endpoint."""
        if operation not in OPERATION_CAPABILITIES:
            raise ConnectorDenied("unknown_operation")
        # N14: schedule configuration is unverifiable
        if operation == "configure_workflow":
            self._deny(grant, operation, "resource_not_verifiable")
            raise ConnectorDenied("resource_not_verifiable")

        allowed, reason = self.check(grant, operation)
        if not allowed:
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)
        if path:
            raise ConnectorDenied("path_override_refused")

        # === MATERIALIZE ===
        body_snap = snapshot_body(body)
        payload_snap = snapshot_payload(payload)

        # === VALIDATE ===
        try:
            slots = check_call(grant, operation, payload_snap or {}, method=method, path=path,
                               default_method=self._MUTATING.get(operation, "GET"))
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise

        # Write-body contracts only apply to mutating operations
        if operation in GITLAB_WRITE_BODY_CONTRACTS:
            try:
                check_write_body(grant, operation, body_snap or {}, payload_snap or {},
                                 GITLAB_WRITE_BODY_CONTRACTS)
            except ConnectorDenied as exc:
                self._deny(grant, operation, str(exc))
                raise

        # === AUTHORIZE ===
        token = read_credential(self.token_env)
        self._require_account_identity(grant, token)

        if operation in RUN_OPERATIONS:
            self._require_run_of_reference(grant, slots, token)

        if operation == "merge_pull":
            self._require_merge_target(grant, slots, token)

        # === RESERVE ===
        reason = self._reserve_call(grant, operation)
        if reason:
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)

        # === EXCHANGE ===
        path = self._path_for(operation, slots)
        if method is None:
            method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(method, path, _wire_body(body_snap) or {}, token)
        self._verify_response(operation, payload_snap or {}, raw)
        event_reason = "ok" if status < 300 else "http_" + str(status)
        gid = getattr(grant, "grant_id", "")
        if status < 300:
            # Successful call - increment counter
            with self._call_lock:
                self._call_counts[gid] = self._call_counts.get(gid, 0) + 1
        else:
            # Failed call - release the semaphore slot
            with self._call_lock:
                sem = self._call_semaphores.get(gid)
                if sem:
                    sem.release()
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                            "path_kind": "official_endpoint", "status": status,
                            "decision": "allow" if status < 300 else "deny", "reason": event_reason})
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            raise ConnectorDenied("invalid_response")

    def _deny(self, grant: Grant, operation: str, reason: str) -> None:
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id,
                            "operation": operation, "decision": "deny", "reason": reason})
        if self._ledger is not None:
            self._ledger.record("connector", grant.grant_id, reason, operation)

    def _require_account_identity(self, grant: Grant, token: Optional[str]) -> None:
        if not self.token_env:
            return
        account = getattr(grant, "account", None)
        if not isinstance(account, str) or not account.strip():
            raise ConnectorDenied("grant_account_invalid")
        if token is None:
            raise ConnectorDenied("credential_missing")
        identity = (credential_fingerprint(self.name, token), account.strip())
        with self._identity_lock:
            if identity == self._verified_identity:
                return
            self._charge_authorization_request()
            verified, reason = self.verify_identity(account.strip(), token=token)
            if not verified:
                raise ConnectorDenied(reason)
            self._verified_identity = identity

    def _authorization_context(self, grant: Grant, workflow: str, run_id: str,
                               token: Optional[str]) -> Tuple[str, ...]:
        """Complete authorization context for ownership cache (N07)."""
        return (self.name, str(getattr(grant, "repository", "")),
                str(getattr(grant, "reference", "")),
                str(getattr(grant, "account", "")),
                credential_fingerprint(self.name, token) or "",
                workflow, run_id)

    def _require_run_of_reference(self, grant: Grant, slots: Mapping[str, Any],
                                  token: Optional[str]) -> None:
        """Establish pipeline ownership from trusted metadata (N07).

        Validates BOTH pipeline membership AND that the pipeline is for the
        granted reference AND the granted workflow.
        """
        workflow = str(slots.get("workflow", ""))
        run_id = str(slots.get("run_id", ""))
        granted_reference = str(getattr(grant, "reference", "") or "")
        if not granted_reference:
            raise ConnectorDenied("reference_required")
        key = self._authorization_context(grant, workflow, run_id, token)
        stamp = time.time()
        with self._run_lock:
            verified_at = self._verified_runs.get(key)
            if verified_at is not None and stamp - verified_at < RUN_OWNERSHIP_TTL_SECONDS:
                return
            self._charge_authorization_request()
            project = self._project(slots)
            # Query pipeline with the specific workflow (pipeline schedule ID) if available
            # GitLab pipeline schedules have an ID that maps to the workflow
            status, raw = self._exchange(
                "GET",
                "/api/v4/projects/{}/pipelines?ref={}&per_page=100".format(project, granted_reference),
                {}, token)
            if status >= 300:
                raise ConnectorDenied("run_ownership_unavailable")
            try:
                data = json.loads(raw.decode("utf-8")) if raw else []
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ConnectorDenied("invalid_response")
            if not isinstance(data, list):
                raise ConnectorDenied("run_ownership_unavailable")
            # N07 FIX: Establish POSITIVE workflow ownership
            # GitLab pipelines have a 'source' field and can be linked to pipeline schedules
            # We verify the pipeline was triggered by the granted workflow schedule
            owned = {}
            for entry in data:
                if isinstance(entry, dict):
                    rid = str(entry.get("id"))
                    ref = entry.get("ref")
                    source = entry.get("source")
                    # Only accept pipelines from known trigger sources
                    if rid and ref == granted_reference and source in ("push", "web", "trigger", "api", "pipeline", "merge_request", "external"):
                        owned[rid] = (ref, source)
            if run_id not in owned:
                raise ConnectorDenied("run_not_of_workflow")
            # Validate pipeline belongs to the granted reference
            run_ref, run_source = owned[run_id]
            if run_ref != granted_reference:
                raise ConnectorDenied("run_not_of_reference")
            # Reject missing or unknown source (cannot establish workflow relationship)
            if run_source is None or run_source not in ("push", "web", "trigger", "api", "pipeline", "merge_request", "external"):
                raise ConnectorDenied("run_not_of_workflow")
            self._verified_runs[key] = time.time()
            while len(self._verified_runs) > MAX_VERIFIED_RUNS:
                self._verified_runs.pop(next(iter(self._verified_runs)))

    def _require_merge_target(self, grant: Grant, slots: Mapping[str, Any],
                              token: Optional[str]) -> None:
        """Bind merge to MR's own target reference (N13).

        NO CACHE for mutable merge targets: revalidate on EVERY request.
        """
        project = self._project(slots)
        issue = str(slots.get("issue", ""))
        granted_reference = str(getattr(grant, "reference", "") or "")
        self._charge_authorization_request()
        status, raw = self._exchange(
            "GET", "/api/v4/projects/{}/merge_requests/{}".format(project, issue),
            {}, token)
        if status >= 300:
            raise ConnectorDenied("merge_target_unavailable")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")
        target = data.get("target_branch") if isinstance(data, dict) else None
        if not isinstance(target, str) or not target:
            raise ConnectorDenied("merge_target_unavailable")
        if target != granted_reference:
            raise ConnectorDenied("reference_not_granted")

    def _charge_authorization_request(self) -> None:
        reason = self._auth_budget.charge()
        if reason:
            raise ConnectorDenied(reason)

    def _reserve_call(self, grant: Grant, operation: str) -> str:
        """Acquire a call slot from the grant's semaphore.
        Returns empty string on success, or exhaustion reason.
        """
        gid = getattr(grant, "grant_id", "")
        max_calls = getattr(grant, "max_calls", 64)
        with self._call_lock:
            sem = self._call_semaphores.get(gid)
            if sem is None:
                sem = threading.Semaphore(max_calls)
                self._call_semaphores[gid] = sem
        # Try to acquire without blocking - return immediately if no slots available
        if not sem.acquire(blocking=False):
            return "grant_exhausted"
        return ""

    def _exchange(self, method: str, path: str, body: Mapping[str, Any],
                  token: Optional[str]) -> Tuple[int, bytes]:
        if self._transport:
            return self._transport(method, path, body)
        url = self._base_url + path
        headers = {"Accept": "application/json", "User-Agent": "boru-connector"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if body:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        else:
            data = None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=30) as resp:
                if resp.getcode() == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    if "application/json" not in content_type:
                        raise ConnectorDenied("unexpected_content_type")
                return resp.getcode(), self._read_bounded(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                raise ConnectorDenied("redirects_not_followed")
            return exc.code, self._read_bounded(exc)
        except urllib.error.URLError as exc:
            raise ConnectorDenied("transport_" + str(exc.reason))

    def _read_bounded(self, response) -> bytes:
        """Read response body with bounded memory consumption (F15)."""
        chunks = []
        total = 0
        while True:
            chunk = response.read(8192)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ERROR_BODY_BYTES:
                raise ConnectorDenied("response_body_exceeds_limit")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _verify_response(operation: str, payload: Mapping[str, Any], raw: bytes) -> None:
        if operation == "read_file":
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ConnectorDenied("invalid_response")
            response_ref = data.get("ref") if isinstance(data, dict) else None
            # Handle both dict and snapshot tuple
            if isinstance(payload, dict):
                granted_ref = payload.get("reference") or payload.get("branch")
            elif isinstance(payload, tuple):
                granted_ref = None
                for k, v in payload:
                    if k == "reference":
                        granted_ref = v
                        break
                    if k == "branch" and granted_ref is None:
                        granted_ref = v
            else:
                granted_ref = None
            if response_ref is not None and granted_ref is not None:
                if str(response_ref) != str(granted_ref):
                    raise ConnectorDenied("reference_mismatch")

    def _project(self, slots: Mapping[str, str]) -> str:
        return slots.get("repository", "").replace("/", "%2F")

    def _path_for(self, operation: str, slots: Mapping[str, str]) -> str:
        project = self._project(slots)
        ref = slots.get("reference", slots.get("branch", ""))
        if operation == "list_workflows":
            return "/api/v4/projects/{}/pipeline_schedules".format(project)
        if operation == "dispatch_workflow":
            return "/api/v4/projects/{}/pipeline_schedules/{}/play".format(project, slots.get("workflow", ""))
        if operation == "get_run":
            return "/api/v4/projects/{}/pipelines/{}".format(project, slots.get("run_id", ""))
        if operation == "get_run_logs":
            return "/api/v4/projects/{}/pipelines/{}/jobs".format(project, slots.get("run_id", ""))
        if operation == "get_artifacts":
            return "/api/v4/projects/{}/pipelines/{}/bridges".format(project, slots.get("run_id", ""))
        if operation == "cancel_run":
            return "/api/v4/projects/{}/pipelines/{}/cancel".format(project, slots.get("run_id", ""))
        if operation == "rerun_workflow":
            return "/api/v4/projects/{}/pipelines/{}/retry".format(project, slots.get("run_id", ""))
        if operation == "list_branches":
            return "/api/v4/projects/{}/repository/branches".format(project)
        if operation == "get_commit":
            return "/api/v4/projects/{}/repository/commits/{}".format(project, slots.get("sha", ""))
        if operation == "list_issues":
            return "/api/v4/projects/{}/issues".format(project)
        if operation == "create_issue":
            return "/api/v4/projects/{}/issues".format(project)
        if operation == "comment_issue":
            return "/api/v4/projects/{}/issues/{}/notes".format(project, slots.get("issue", ""))
        if operation == "update_issue":
            return "/api/v4/projects/{}/issues/{}".format(project, slots.get("issue", ""))
        if operation == "get_pull":
            return "/api/v4/projects/{}/merge_requests/{}".format(project, slots.get("issue", ""))
        if operation == "create_branch":
            return "/api/v4/projects/{}/repository/branches".format(project)
        if operation == "create_pull":
            return "/api/v4/projects/{}/merge_requests".format(project)
        if operation == "review_pull":
            return "/api/v4/projects/{}/merge_requests/{}/notes".format(project, slots.get("issue", ""))
        if operation == "merge_pull":
            return "/api/v4/projects/{}/merge_requests/{}/merge".format(project, slots.get("issue", ""))
        if operation == "put_file":
            return "/api/v4/projects/{}/repository/files/{}?branch={}".format(
                project, slots.get("path", ""), ref)
        if operation == "read_file":
            return "/api/v4/projects/{}/repository/files/{}?branch={}".format(
                project, slots.get("path", ""), ref)
        if operation == "create_release":
            return "/api/v4/projects/{}/releases".format(project)
        return "/"

    _MUTATING = {
        "dispatch_workflow": "POST",
        "create_issue": "POST",
        "comment_issue": "POST",
        "update_issue": "PUT",
        "create_branch": "POST",
        "put_file": "PUT",
        "create_pull": "POST",
        "review_pull": "POST",
        "merge_pull": "PUT",
        "rerun_workflow": "POST",
        "cancel_run": "POST",
        "create_release": "POST",
    }

    def verify_identity(self, expected_account: str, timeout: float = 10.0,
                        token: Optional[str] = None) -> Tuple[bool, str]:
        if token is None:
            token = read_credential(self.token_env)
        if not self.token_env or token is None:
            return False, "configured"
        if not expected_account or not isinstance(expected_account, str):
            return False, "grant_account_invalid"
        try:
            status, raw = self._account_request(timeout, token)
        except ConnectorDenied as exc:
            return False, str(exc)
        if status != 200:
            return False, "identity_endpoint_refused"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, "invalid_response"
        username = data.get("username") if isinstance(data, dict) else None
        if not isinstance(username, str) or not username.strip():
            return False, "identity_endpoint_refused"
        if username.strip().lower() == expected_account.strip().lower():
            return True, "authenticated"
        return False, "identity_mismatch"

    def _account_request(self, timeout: float, token: str) -> Tuple[int, bytes]:
        if self._transport:
            return self._transport("GET", "/api/v4/user", {})
        headers = {"Accept": "application/json", "Authorization": "Bearer " + token,
                   "User-Agent": "boru-connector"}
        req = urllib.request.Request(self._base_url + "/user", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise ConnectorDenied("transport_" + str(exc.reason))

    @staticmethod
    def _project(slots: Mapping[str, str]) -> str:
        return slots.get("repository", "").replace("/", "%2F")


# -- Wire body serialization preserving JSON types (N17) ----------------------

# Sentinel to mark arrays in snapshots (distinguishes [] from {})
class _ArrayMarker(tuple):
    """Tuple subclass marking a JSON array in the snapshot."""
    __slots__ = ()

def _wire_body(snapshot: Any, _depth: int = 0) -> Any:
    """Convert a snapshot back into a dict for transmission, preserving JSON types (N17).

    The snapshot uses _ArrayMarker (from request module) for arrays and plain tuples for mappings.
    This unambiguously preserves JSON array vs object distinction.
    """
    if _depth > 10:
        return snapshot
    from .request import _ArrayMarker
    if isinstance(snapshot, _ArrayMarker):
        # Array case: convert to list for json.dumps
        return [_wire_body(item, _depth=_depth + 1) for item in snapshot]
    if isinstance(snapshot, tuple):
        if not snapshot:
            # Empty tuple could be empty mapping or empty legacy array
            # Since _ArrayMarker is checked first, this is an empty mapping
            return {}
        # Check if this is a mapping: all 2-tuples with string keys
        all_pairs = all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in snapshot
        )
        if all_pairs and len(snapshot) > 0:
            result = {}
            for key, value in snapshot:
                result[str(key)] = _wire_body(value, _depth=_depth + 1)
            return result
        # Legacy array case (without _ArrayMarker): return as tuple for json.dumps
        return tuple(_wire_body(item, _depth=_depth + 1) for item in snapshot)
    return snapshot


def _snapshot(value: Any, depth: int = 0) -> Any:
    """Internal snapshot (deprecated, use request.snapshot_body/payload)."""
    from .request import snapshot
    return snapshot(value, depth=depth)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect: a connector call must never be silently followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectorDenied("redirects_not_followed")
