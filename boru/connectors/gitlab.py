"""Official GitLab REST connector (P8 source slice) — typed, grant-bound.

GitLab.com and owner-allowlisted self-managed instances. Same rules as the
GitHub connector: a denied operation produces no outbound request, tokens only
enter through an environment-variable name, and a token is identity only.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .scope import (
    GITLAB_WRITE_BODY_CONTRACTS, check_call, check_dispatch_body, check_write_body,
)

API_BASE = "https://gitlab.com"
MAX_PAGE = 100

#: Operations that address one pipeline.  A pipeline's ownership is established
#: from trusted provider metadata - the pipelines of the **granted reference** -
#: before it is addressed, because a caller-declared workflow name says nothing
#: about which pipeline an id names (N07).
RUN_OPERATIONS = frozenset({"get_run", "get_run_logs", "get_artifacts",
                            "cancel_run", "rerun_workflow"})

#: A verified (workflow, run) pair is remembered so one operation does not
#: re-query, and the memo is bounded.
MAX_VERIFIED_RUNS = 64

#: N06: authorization traffic (identity verification and ownership lookups) is
#: bounded **as requests**, not only as stored entries.
MAX_AUTHORIZATION_REQUESTS = 512

#: N06: a verified ownership entry is evidence for a bounded time only.
RUN_OWNERSHIP_TTL_SECONDS = 300.0

#: N12: a validated write body is copied before authorization and that exact
#: snapshot is what reaches the transport.
MAX_SNAPSHOT_DEPTH = 3
#: An error body is diagnostic, never a payload: keep only a bounded prefix.
MAX_ERROR_BODY_BYTES = 4 * 1024


def _snapshot(value: Any, depth: int = 0) -> Any:
    """A bounded, immutable copy of a validated request body (N12)."""
    if depth > MAX_SNAPSHOT_DEPTH:
        raise ConnectorDenied("body_nested_too_deeply")
    if isinstance(value, Mapping):
        return tuple((key, _snapshot(item, depth + 1))
                     for key, item in sorted(value.items(), key=lambda pair: str(pair[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_snapshot(item, depth + 1) for item in value)
    return value


def _wire_body(snapshot: Any) -> Any:
    """The wire form of a validated body snapshot."""
    if isinstance(snapshot, tuple) and not snapshot:
        return {}
    if isinstance(snapshot, tuple):
        return {str(key): _wire_body(item) for key, item in snapshot}
    return snapshot


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
        # Call accounting is shared by every path that reaches an endpoint, so
        # a ceiling check and its reservation cannot interleave (N06).
        self._call_lock = threading.Lock()
        self._identity_lock = threading.Lock()
        # N07: (workflow, run) pairs whose ownership the provider itself
        # confirmed, bounded.  Authorization traffic of this kind is bounded
        # separately from the grant's repository-operation ceiling (N06).
        self._authorization_requests = 0
        # N07: the ownership memo is keyed by the complete authorization
        # context - repository, granted reference, verified account, credential
        # fingerprint, workflow and run id - so evidence established under one
        # context can never authorize the same run id under another.
        self._verified_runs: Dict[Tuple[str, str, str, str, str, str, str], float] = {}
        self._run_lock = threading.Lock()
        # The verified identity: the (token fingerprint, account) pair that was
        # actually checked.  Binding the account too is what stops a second
        # grant naming another account behind the same token from being waved
        # through on the first account's verification (F07).
        self._verified_identity: Optional[Tuple[str, str]] = None

    def capabilities(self) -> Tuple[Capability, ...]:
        return tuple(OPERATION_CAPABILITIES.values())

    def connection_state(self) -> str:
        if self.token_env and os.environ.get(self.token_env):
            return "authenticated"
        if self.token_env:
            return "configured"
        return "disconnected"

    def verify_identity(self, expected_account: str, timeout: float = 10.0,
                        token: Optional[str] = None) -> Tuple[bool, str]:
        """Verify the account behind the token against the grant's account.

        ``token`` is the credential snapshot for this request; when it is not
        supplied it is read once here, exactly as the caller would.
        """
        if token is None:
            token = self._token_value()
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
        if operation == "configure_workflow":
            # N14: a pipeline schedule cannot be verified as belonging to the
            # grant, so the operation is refused instead of acting on an
            # unchecked resource.
            self._deny(grant, operation, "resource_not_verifiable")
            raise ConnectorDenied("resource_not_verifiable")
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
        # Every write body is validated against this provider's operation
        # contract before any transport is constructed (N08/N11).
        try:
            check_write_body(grant, operation, body or {}, payload or {},
                             GITLAB_WRITE_BODY_CONTRACTS)
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise
        # N12: the validated body becomes an immutable snapshot here, before any
        # authorization request runs, and that exact snapshot is transmitted.
        snapshot = _snapshot(body) if body is not None else None
        # The credential is read once for this authorized request, and that
        # exact value is the one fingerprinted, verified and transmitted (F07).
        token = self._token_value()
        # A token proves an identity, never write or Shell authorization.
        self._require_account_identity(grant, token)
        # A pipeline is addressed only after the provider's own metadata
        # confirms it belongs to the granted reference (N07).
        if operation in RUN_OPERATIONS:
            self._require_run_of_reference(grant, slots, token)
        # A merge is addressed only after the merge request's own target
        # reference is read from trusted provider metadata (N13).
        if operation == "merge_pull":
            self._require_merge_target(grant, slots, token)
        # The repository-operation ceiling is reserved atomically, before the
        # repository exchange.  Identity and ownership verification are
        # authorization traffic with their own bounded budget, and the grant's
        # ``max_calls`` bounds repository operations (N06).
        reason = self._reserve_call(grant, operation)
        if reason:
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)
        path = self._path_for(operation, slots)
        if method is None:
            method = self._MUTATING.get(operation, "GET")
        status, raw = self._exchange(method, path, _wire_body(snapshot) or {}, token)
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

    def _require_account_identity(self, grant: Grant, token: Optional[str]) -> None:
        """Verify the account behind the token for this grant.

        ``token`` is the snapshot this request read once: the same value is
        verified here and transmitted later, so a credential that was never
        verified cannot ride out (F07).  The remembered identity is the
        verified **(token fingerprint, account)** pair, and a
        configured-but-absent credential never passes the guard.
        """
        if not self.token_env:
            # No credential channel is configured at all: an in-process or
            # test configuration, which ``connection_state`` reports honestly
            # as ``disconnected``.  A configured channel is never waved through.
            return
        account = getattr(grant, "account", None)
        if not isinstance(account, str) or not account.strip():
            raise ConnectorDenied("grant_account_invalid")
        if token is None:
            raise ConnectorDenied("credential_missing")
        identity = (self._token_fingerprint(self.name, token), account.strip())
        with self._identity_lock:
            if identity == self._verified_identity:
                return
            self._charge_authorization_request()
            verified, reason = self.verify_identity(account.strip(), token=token)
            if not verified:
                raise ConnectorDenied(reason)
            # Only an actually verified (token, account) pair is remembered.
            self._verified_identity = identity

    def _authorization_context(self, grant: Grant, workflow: str, run_id: str,
                               token: Optional[str]) -> Tuple[str, ...]:
        """The complete context an ownership decision belongs to (N07).

        The reference comes from the **grant**, never from the caller's slots:
        a request that names no reference cannot establish ownership under the
        granted one.  The context carries the repository, granted reference,
        verified account, credential fingerprint, workflow and run id, so
        evidence established under one context never authorizes another.
        """
        return (self.name, str(getattr(grant, "repository", "")),
                str(getattr(grant, "reference", "")),
                str(getattr(grant, "account", "")),
                self._token_fingerprint(self.name, token) or "",
                workflow, run_id)

    def _require_run_of_reference(self, grant: Grant, slots: Mapping[str, Any],
                                  token: Optional[str]) -> None:
        """Establish from trusted metadata that this pipeline belongs to the
        grant (N07).

        A caller-declared workflow name proves nothing about which pipeline an
        id names, so the pipeline is addressed only after the pipelines of the
        **granted reference** - the official endpoint's answer, not the
        caller's claim - contain the requested id.  Evidence is remembered per
        complete authorization context for a bounded time, and concurrent
        lookups of the same context are coalesced under the lock (N06).
        Missing or malformed evidence refuses.
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
            status, raw = self._exchange(
                "GET",
                "/api/v4/projects/{}/pipelines?ref={}&per_page=100".format(project,
                                                                          granted_reference),
                {}, token)
            if status >= 300:
                raise ConnectorDenied("run_ownership_unavailable")
            try:
                data = json.loads(raw.decode("utf-8")) if raw else []
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ConnectorDenied("invalid_response")
            if not isinstance(data, list):
                raise ConnectorDenied("run_ownership_unavailable")
            owned = {str(entry.get("id")) for entry in data if isinstance(entry, dict)}
            if run_id not in owned:
                raise ConnectorDenied("run_not_of_workflow")
            self._verified_runs[key] = time.time()
            while len(self._verified_runs) > MAX_VERIFIED_RUNS:
                self._verified_runs.pop(next(iter(self._verified_runs)))

    def _require_merge_target(self, grant: Grant, slots: Mapping[str, Any],
                              token: Optional[str]) -> None:
        """Bind a merge to the merge request's own target reference (N13).

        A grant binds a repository and a reference, but a merge is addressed by
        a numeric id: without this check a merge request targeting another
        branch could be merged under a grant that never authorized it.  The
        destination is read from trusted provider metadata first.
        """
        project = self._project(slots)
        issue = str(slots.get("issue", ""))
        granted_reference = str(getattr(grant, "reference", "") or "")
        context = ("merge_target", self.name, str(getattr(grant, "repository", "")),
                   granted_reference, str(getattr(grant, "account", "")),
                   self._token_fingerprint(self.name, token) or "", issue)
        stamp = time.time()
        with self._run_lock:
            verified_at = self._verified_runs.get(context)
            if verified_at is not None and stamp - verified_at < RUN_OWNERSHIP_TTL_SECONDS:
                return
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
            self._verified_runs[context] = time.time()
            while len(self._verified_runs) > MAX_VERIFIED_RUNS:
                self._verified_runs.pop(next(iter(self._verified_runs)))

    def _charge_authorization_request(self) -> None:
        """Count one authorization request against the instance's bound (N06).

        A bounded cache bounds stored entries, not requests: a flood of identity
        mismatches or foreign pipelines would otherwise issue unbounded
        authorization traffic.
        """
        with self._call_lock:
            self._authorization_requests += 1
            if self._authorization_requests > MAX_AUTHORIZATION_REQUESTS:
                raise ConnectorDenied("authorization_traffic_exhausted")

    def _reserve_call(self, grant: Grant, operation: str) -> str:
        """Atomically verify the grant ceiling and reserve one call slot.

        The check and the increment share one lock, so a burst of concurrent
        calls cannot pass the ceiling together.  This reserves a **repository
        operation**: identity and ownership verification are authorization
        traffic, bounded separately by ``_charge_authorization_request`` (N06).
        """
        with self._call_lock:
            allowed, reason = self.check(grant, operation)
            if not allowed:
                return reason
            self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
            return ""

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
            # N14: a rerun retries the pipeline whose ownership was just
            # verified.  Addressing a *schedule* here acted on a resource that
            # was never checked, so schedule execution is a distinct typed
            # operation this grant matrix does not carry.
            "rerun_workflow": "/api/v4/projects/{}/pipelines/{}/retry".format(project, run_id),
            "cancel_run": "/api/v4/projects/{}/pipelines/{}/cancel".format(project, run_id),
            "get_run": "/api/v4/projects/{}/pipelines/{}".format(project, run_id),
            "get_run_logs": "/api/v4/projects/{}/pipelines/{}/jobs".format(project, run_id),
            "get_artifacts": "/api/v4/projects/{}/pipelines/{}/bridges".format(project, run_id),
            # N14: schedule configuration is deliberately absent.  A pipeline
            # schedule is a resource no ownership check can verify here, so the
            # operation is refused rather than acting on an unchecked target.
            "create_release": "/api/v4/projects/{}/releases".format(project),
        }
        return paths.get(operation, "")

    def _account_request(self, timeout: float, token: Optional[str] = None) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport("GET", "/api/v4/user", {})
        opener = urllib.request.build_opener(_NoRedirect)
        headers = {"Accept": "application/json", "User-Agent": "tihulu-boru-core"}
        if token is None:
            token = self._token_value()
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

    def _exchange(self, method: str, path: str, body: Mapping[str, Any],
                  token: Optional[str] = None) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(method, path, body)
        if not self.base_url.lower().startswith("https://") and not self.allow_http_endpoints:
            raise ConnectorDenied("insecure_endpoint")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "User-Agent": "tihulu-boru-core"}
        if token is None:
            token = self._token_value()
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
