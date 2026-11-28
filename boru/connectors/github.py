"""Official GitHub REST connector (P8 source slice) — typed, grant-bound.

Centralized authorization architecture (N12/N15/N07/N13/N06):
1. **Materialize once**: snapshot body + payload before any validation
2. **Validate snapshot**: all grant checks, write-body contracts against snapshot
3. **Authorize snapshot**: identity, run ownership, merge target, branch source
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
    GITHUB_WRITE_BODY_CONTRACTS, check_call, check_dispatch_body, check_write_body,
    _payload_get,
)
from .request import (
    snapshot_body, snapshot_payload, read_credential, credential_fingerprint,
    AuthorizationBudget, MAX_SNAPSHOT_DEPTH,
)

API_BASE = "https://api.github.com"
MAX_ERROR_BODY_BYTES = 4 * 1024

RUN_OPERATIONS = frozenset({"get_run", "get_run_logs", "get_artifacts",
                            "cancel_run", "rerun_workflow"})

MAX_VERIFIED_RUNS = 64
MAX_AUTHORIZATION_REQUESTS = 512
RUN_OWNERSHIP_TTL_SECONDS = 300.0


class GitHubProvider(RepositoryProvider):
    """GitHub REST API v3 connector bound by owner-issued grants."""

    def __init__(self, *, token_env: Optional[str] = None, base_url: str = API_BASE,
                 transport=None, allow_http: bool = False, audit=None):
        if token_env is not None and (not isinstance(token_env, str) or not token_env.strip() or len(token_env) > 64):
            raise PolicyViolation("token_env must be a bounded environment variable name")
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise PolicyViolation("base_url must be a bounded non-empty string")
        if not base_url.lower().startswith("https://") and not allow_http:
            raise PolicyViolation("GitHub API requires https")
        self.name = "github"
        self.token_env = token_env
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._allow_http = allow_http
        self._audit: List[Dict[str, Any]] = []
        self._ledger = audit
        # Identity cache: (token_fingerprint, account) -> verified
        self._verified_identity: Optional[Tuple[str, str]] = None
        self._identity_lock = threading.Lock()
        # N07: ownership cache keyed by complete authorization context
        self._verified_runs: Dict[Tuple[str, ...], float] = {}
        self._run_lock = threading.Lock()
        # N06: centralized authorization budget
        self._auth_budget = AuthorizationBudget(MAX_AUTHORIZATION_REQUESTS)
        # Repository-operation ceiling
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

    def list_workflows_typed(self, grant, payload=None, timeout: float = 10.0) -> List[Any]:
        """Discover workflows through the official endpoint (issue #9)."""
        allowed, reason = self.check(grant, "list_workflows")
        if not allowed:
            raise ConnectorDenied(reason)
        # Materialize: snapshot payload before any auth
        snap = snapshot_payload(payload)
        # Validate snapshot against grant
        slots = check_call(grant, "list_workflows", snap or {}, method=None, path="",
                           default_method="GET")
        # Credential snapshot: one read for this request
        token = read_credential(self.token_env)
        # Authorize: identity verification
        self._require_account_identity(grant, token)
        # Reserve repository-operation slot
        reason = self._reserve_call(grant, "list_workflows")
        if reason:
            self._deny(grant, "list_workflows", reason)
            raise ConnectorDenied(reason)
        # Exchange: transmit snapshot
        status, raw = self._exchange("list_workflows", "GET",
                                     self._path_for("list_workflows", slots), {},
                                     token)
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        # Increment successful call counter
        gid = getattr(grant, "grant_id", "")
        with self._call_lock:
            self._call_counts[gid] = self._call_counts.get(gid, 0) + 1
        from .workflows import parse_workflows
        try:
            return parse_workflows(json.loads(raw.decode("utf-8")) if raw else {})
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")

    def call(self, grant: Grant, operation: str, payload: Optional[Mapping[str, Any]] = None,
             body: Optional[Mapping[str, Any]] = None, method: Optional[str] = None,
             path: Optional[str] = None) -> Any:
        """Execute a grant-bound operation against the official GitHub endpoint."""
        # Gate: grant allows this operation
        allowed, reason = self.check(grant, operation)
        if not allowed:
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)
        if path:
            raise ConnectorDenied("path_override_refused")

        # === MATERIALIZE: snapshot body + payload BEFORE any validation ===
        body_snap = snapshot_body(body)
        payload_snap = snapshot_payload(payload)

        # === VALIDATE: all grant checks against the snapshot ===
        try:
            slots = check_call(grant, operation, payload_snap or {}, method=method, path=path,
                               default_method=self._MUTATING.get(operation, "GET"))
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise

        # Write-body contracts only apply to mutating operations
        if operation in GITHUB_WRITE_BODY_CONTRACTS:
            try:
                check_write_body(grant, operation, body_snap or {}, payload_snap or {},
                                 GITHUB_WRITE_BODY_CONTRACTS)
            except ConnectorDenied as exc:
                self._deny(grant, operation, str(exc))
                raise

        # === AUTHORIZE: all checks against the snapshot ===
        token = read_credential(self.token_env)
        self._require_account_identity(grant, token)

        if operation in RUN_OPERATIONS:
            self._require_run_of_workflow(grant, slots, token)

        if operation == "create_branch":
            self._require_branch_source(grant, payload_snap, body_snap, token)

        if operation == "merge_pull":
            self._require_merge_target(grant, slots, token)

        # === RESERVE: repository-operation ceiling ===
        reason = self._reserve_call(grant, operation)
        if reason:
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)

        # === EXCHANGE: transmit the validated snapshot ===
        path = self._path_for(operation, slots)
        if method is None:
            method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(operation, method, path, _wire_body(body_snap) or {}, token)
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

    def _require_branch_source(self, grant: Grant, payload: Mapping[str, Any],
                               body: Mapping[str, Any], token: Optional[str]) -> None:
        """Bind a branch creation to the granted reference's own head (N08/N12)."""
        self._charge_authorization_request()
        reference = str(getattr(grant, "reference", "") or "")
        # Handle both dict and snapshot tuple
        if isinstance(body, dict):
            target = body.get("ref")
        elif isinstance(body, tuple):
            target = None
            for k, v in body:
                if k == "ref":
                    target = v
                    break
        else:
            target = None
        if not isinstance(target, str) or len(target) > 128 \
                or any(ord(c) < 0x20 or ord(c) == 0x7F for c in target):
            raise ConnectorDenied("unsafe_body_value")
        prefix = "refs/heads/"
        if not target.startswith(prefix):
            raise ConnectorDenied("unsafe_body_value")
        name = target[len(prefix):]
        if not name or len(name) > 64 or "/" in name or name in (".", "..") \
                or name.strip() != name:
            raise ConnectorDenied("unsafe_body_value")
        repository = self._repository(payload)
        status, raw = self._exchange("get_reference_head", "GET",
                                     "/repos/{}/git/ref/heads/{}".format(repository, reference),
                                     {}, token)
        if status >= 300:
            raise ConnectorDenied("reference_head_unavailable")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")
        head = data.get("object", {}).get("sha") if isinstance(data, dict) else None
        if not isinstance(head, str) or not head:
            raise ConnectorDenied("reference_head_unavailable")
        # Handle both dict and snapshot tuple for payload
        if isinstance(payload, dict):
            declared = payload.get("sha")
        elif isinstance(payload, tuple):
            declared = None
            for k, v in payload:
                if k == "sha":
                    declared = v
                    break
        else:
            declared = None
        if declared is not None and str(declared) != head:
            raise ConnectorDenied("reference_not_granted")

        # Handle both dict and snapshot tuple for body
        if isinstance(body, dict):
            body_sha = body.get("sha", "")
        elif isinstance(body, tuple):
            body_sha = None
            for k, v in body:
                if k == "sha":
                    body_sha = v
                    break
            if body_sha is None:
                body_sha = ""
        else:
            body_sha = ""
        if str(body_sha) != head:
            raise ConnectorDenied("reference_not_granted")

    def _authorization_context(self, grant: Grant, workflow: str, run_id: str,
                               token: Optional[str]) -> Tuple[str, ...]:
        """Complete authorization context for ownership cache (N07)."""
        return (self.name, str(getattr(grant, "repository", "")),
                str(getattr(grant, "reference", "")),
                str(getattr(grant, "account", "")),
                credential_fingerprint(self.name, token) or "",
                workflow, run_id)

    def _require_run_of_workflow(self, grant: Grant, slots: Mapping[str, Any],
                                 token: Optional[str]) -> None:
        """Establish run ownership from trusted metadata (N07).

        Validates BOTH workflow membership AND that the run's head_branch
        matches the granted reference.
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
            repository = self._repository(slots)
            status, raw = self._exchange(
                "list_workflow_runs", "GET",
                "/repos/{}/actions/workflows/{}/runs?per_page=100".format(repository, workflow),
                {}, token)
            if status >= 300:
                raise ConnectorDenied("run_ownership_unavailable")
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ConnectorDenied("invalid_response")
            runs = data.get("workflow_runs") if isinstance(data, dict) else None
            if not isinstance(runs, list):
                raise ConnectorDenied("run_ownership_unavailable")
            # N07 FIX: validate BOTH run ID AND head_branch
            owned = {}
            for entry in runs:
                if isinstance(entry, dict):
                    rid = str(entry.get("id"))
                    branch = entry.get("head_branch")
                    if rid:
                        owned[rid] = branch
            if run_id not in owned:
                raise ConnectorDenied("run_not_of_workflow")
            # Validate run belongs to the granted reference
            run_branch = owned[run_id]
            if run_branch != granted_reference:
                raise ConnectorDenied("run_not_of_reference")
            self._verified_runs[key] = time.time()
            while len(self._verified_runs) > MAX_VERIFIED_RUNS:
                self._verified_runs.pop(next(iter(self._verified_runs)))

    def _require_merge_target(self, grant: Grant, slots: Mapping[str, Any],
                              token: Optional[str]) -> None:
        """Bind merge to PR's own target reference (N13).

        NO CACHE for mutable merge targets: revalidate on EVERY request.
        """
        repository = self._repository(slots)
        issue = str(slots.get("issue", ""))
        granted_reference = str(getattr(grant, "reference", "") or "")
        self._charge_authorization_request()
        status, raw = self._exchange("get_pull", "GET",
                                     "/repos/{}/pulls/{}".format(repository, issue),
                                     {}, token)
        if status >= 300:
            raise ConnectorDenied("merge_target_unavailable")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")
        base = data.get("base") if isinstance(data, dict) else None
        target = base.get("ref") if isinstance(base, dict) else None
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

    def _exchange(self, operation: str, method: str, path: str,
                  body: Mapping[str, Any], token: Optional[str]) -> Tuple[int, bytes]:
        if self._transport:
            return self._transport(method, path, body)
        url = self._base_url + path
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "boru-connector"}
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

    def _path_for(self, operation: str, slots: Mapping[str, str]) -> str:
        repo = slots.get("repository", "")
        if operation == "list_workflows":
            return "/repos/{}/actions/workflows".format(repo)
        if operation == "dispatch_workflow":
            return "/repos/{}/actions/workflows/{}/dispatches".format(repo, slots.get("workflow", ""))
        if operation == "get_run":
            return "/repos/{}/actions/runs/{}".format(repo, slots.get("run_id", ""))
        if operation == "get_run_logs":
            return "/repos/{}/actions/runs/{}/logs".format(repo, slots.get("run_id", ""))
        if operation == "get_artifacts":
            return "/repos/{}/actions/runs/{}/artifacts".format(repo, slots.get("run_id", ""))
        if operation == "cancel_run":
            return "/repos/{}/actions/runs/{}/cancel".format(repo, slots.get("run_id", ""))
        if operation == "rerun_workflow":
            return "/repos/{}/actions/runs/{}/rerun".format(repo, slots.get("run_id", ""))
        if operation == "list_branches":
            return "/repos/{}/branches".format(repo)
        if operation == "get_commit":
            return "/repos/{}/commits/{}".format(repo, slots.get("sha", ""))
        if operation == "list_issues":
            return "/repos/{}/issues".format(repo)
        if operation == "create_issue":
            return "/repos/{}/issues".format(repo)
        if operation == "comment_issue":
            return "/repos/{}/issues/{}/comments".format(repo, slots.get("issue", ""))
        if operation == "update_issue":
            return "/repos/{}/issues/{}".format(repo, slots.get("issue", ""))
        if operation == "get_pull":
            return "/repos/{}/pulls/{}".format(repo, slots.get("issue", ""))
        if operation == "create_branch":
            return "/repos/{}/git/refs".format(repo)
        if operation == "create_pull":
            return "/repos/{}/pulls".format(repo)
        if operation == "review_pull":
            return "/repos/{}/pulls/{}/reviews".format(repo, slots.get("issue", ""))
        if operation == "merge_pull":
            return "/repos/{}/pulls/{}/merge".format(repo, slots.get("issue", ""))
        if operation == "put_file":
            ref = slots.get("reference", slots.get("branch", ""))
            return "/repos/{}/contents/{}?ref={}".format(repo, slots.get("path", ""), ref)
        if operation == "read_file":
            ref = slots.get("reference", slots.get("branch", ""))
            return "/repos/{}/contents/{}?ref={}".format(repo, slots.get("path", ""), ref)
        if operation == "create_release":
            return "/repos/{}/releases".format(repo)
        return "/"

    _MUTATING = {
        "dispatch_workflow": "POST",
        "create_issue": "POST",
        "comment_issue": "POST",
        "update_issue": "PATCH",
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
        login = data.get("login") if isinstance(data, dict) else None
        if not isinstance(login, str) or not login.strip():
            return False, "identity_endpoint_refused"
        if login.strip().lower() == expected_account.strip().lower():
            return True, "authenticated"
        return False, "identity_mismatch"

    def _account_request(self, timeout: float, token: str) -> Tuple[int, bytes]:
        if self._transport:
            return self._transport("GET", "/user", {})
        headers = {"Accept": "application/vnd.github+json",
                   "Authorization": "Bearer " + token,
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
    def _repository(payload: Mapping[str, Any]) -> str:
        from .scope import RepositoryRef

        return RepositoryRef.parse(str(_payload_get(payload, "repository"))).encoded()


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


# -- Constructor sentinel for internal use -----------------------------------
def _snapshot(value: Any, depth: int = 0) -> Any:
    """Internal snapshot function (deprecated, use request.snapshot_body/payload)."""
    from .request import snapshot
    return snapshot(value, depth=depth)


def read_only_denies(provider: GitHubProvider, grant: Grant) -> List[str]:
    """Return every operation the given grant refuses, without any request."""
    refused = []
    for operation in OPERATION_CAPABILITIES:
        allowed, _ = provider.check(grant, operation)
        if not allowed:
            refused.append(operation)
    return refused


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect: a connector call must never be silently followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectorDenied("redirects_not_followed")
