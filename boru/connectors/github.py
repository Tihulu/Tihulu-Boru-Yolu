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
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..errors import ConnectorDenied, PolicyViolation
from .base import OPERATION_CAPABILITIES, Capability, Grant, RepositoryProvider
from .request import freeze_mapping, wire_body
from .scope import (
    GITHUB_WRITE_BODY_CONTRACTS, check_call, check_dispatch_body, check_write_body,
)

API_BASE = "https://api.github.com"
#: An error body is diagnostic, never a payload: keep only a bounded prefix.
MAX_ERROR_BODY_BYTES = 4 * 1024

#: Operations that address one run of a granted workflow.  A run's ownership is
#: established from **trusted provider metadata** - the workflow's own runs
#: list - before the run is addressed, because a caller-declared workflow name
#: says nothing about which run an id names (N07).
RUN_OPERATIONS = frozenset({"get_run", "get_run_logs", "get_artifacts",
                            "cancel_run", "rerun_workflow"})

#: A verified (workflow, run) pair is remembered so one operation does not
#: re-query the workflow's runs, and the memo is bounded: a long-lived process
#: cannot grow it without limit.
MAX_VERIFIED_RUNS = 64

#: N06: authorization traffic (identity verification and ownership lookups) is
#: bounded **as requests**, not only as stored entries: past this ceiling the
#: connector refuses rather than issuing unbounded authorization requests.
MAX_AUTHORIZATION_REQUESTS = 512

#: N06: a verified ownership entry is evidence for a bounded time only; past
#: the window the ownership is re-established, so a credential rotation or a
#: changed grant cannot ride on stale evidence.
RUN_OWNERSHIP_TTL_SECONDS = 300.0

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


class GitHubProvider(RepositoryProvider):
    """Official GitHub API connector with grant-bound typed operations."""

    name = "github"

    def __init__(self, *, token_env: Optional[str] = None, base_url: str = API_BASE,
                 transport=None, allow_http: bool = False, audit=None) -> None:
        # allow_http is an owner opt-in for pinned loopback test endpoints only.
        self.allow_http_endpoints = allow_http
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
        # Call accounting is shared by every path that reaches an endpoint, so
        # a ceiling check and its reservation cannot interleave (N06).
        self._call_lock = threading.Lock()
        # The verified identity: the (token fingerprint, account) pair that was
        # actually checked.  Binding the account too is what stops a second
        # grant naming another account behind the same token from being waved
        # through on the first account's verification (F07).
        self._verified_identity: Optional[Tuple[str, str]] = None
        self._identity_lock = threading.Lock()
        # N06: a bounded count of the authorization requests this instance has
        # made, so a flood of identity mismatches or foreign runs cannot issue
        # unbounded authorization traffic.
        self._authorization_requests = 0
        # N07: (authorization context) -> the time ownership was confirmed.
        # The key carries the **whole** context — repository, granted
        # reference, verified account, credential fingerprint, workflow and
        # run id — so an entry verified under one context can never authorize
        # the same run under another.
        self._verified_runs: Dict[Tuple[str, str, str, str, str, str, str], float] = {}
        self._run_lock = threading.Lock()

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

    def list_workflows_typed(self, grant, payload=None, timeout: float = 10.0) -> List[Any]:
        """Discover workflows through the official endpoint (issue #9)."""
        allowed, reason = self.check(grant, "list_workflows")
        if not allowed:
            raise ConnectorDenied(reason)
        slots = check_call(grant, "list_workflows", payload, method=None, path="",
                           default_method="GET")
        # Discovery is an externally connected path like any other: the identity
        # behind the token is verified before the request, and the call counts
        # against the grant's ceiling.  The credential is read **once** and that
        # exact snapshot is verified and transmitted (F07/N02).
        token = self._token_value()
        self._require_account_identity(grant, token)
        reason = self._reserve_call(grant, "list_workflows")
        if reason:
            self._deny(grant, "list_workflows", reason)
            raise ConnectorDenied(reason)
        status, raw = self._exchange("list_workflows", "GET",
                                     self._path_for("list_workflows", slots), {},
                                     token)
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        from .workflows import parse_workflows

        try:
            return parse_workflows(json.loads(raw.decode("utf-8")) if raw else {})
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")

    def verify_identity(self, expected_account: str, timeout: float = 10.0,
                        token: Optional[str] = None) -> Tuple[bool, str]:
        """Verify the account behind the token against the grant's account.

        ``token`` is the credential snapshot for this request; when it is not
        supplied it is read once here, exactly as the caller would.  A token
        proves an identity, never write or Shell authorization; a mismatch is
        reported instead of silently accepted.
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
        login = data.get("login")
        if not isinstance(login, str) or not login.strip():
            return False, "identity_endpoint_refused"
        if login != expected_account:
            return False, "identity_mismatch"
        return True, "authenticated"

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
            self._deny(grant, operation, reason)
            raise ConnectorDenied(reason)
        # The requested repository/reference must be the granted one, and no raw
        # method/path override may reach the official endpoint (issue #15).
        if path:
            raise ConnectorDenied("path_override_refused")
        try:
            # The slots returned here are the only values used to build the
            # request: what was checked is what is sent.
            slots = check_call(grant, operation, payload, method=method, path=path,
                               default_method=self._MUTATING.get(operation, "GET"))
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise
        # Every write body is validated against this provider's operation
        # contract before any transport is constructed: the reference that was
        # checked is the reference that is sent, a key the operation does not
        # document never reaches the endpoint, and a mandatory reference key
        # cannot be omitted (N08/N11).
        try:
            snapshot = freeze_mapping(body)
            check_write_body(grant, operation, snapshot, slots,
                             GITHUB_WRITE_BODY_CONTRACTS)
        except ConnectorDenied as exc:
            self._deny(grant, operation, str(exc))
            raise
        # The credential is read **once** for this authorized request and that
        # exact value is the one fingerprinted, verified and transmitted: a
        # rotation mid-request cannot make the connector send a credential
        # that was never verified (F07).
        token = self._token_value()
        # A token proves an identity, never write or Shell authorization: the
        # account behind it must match the grant's account before a request.
        self._require_account_identity(grant, token)
        # A run is addressed only after the provider's own metadata confirms it
        # belongs to the granted workflow (N07).
        if operation in RUN_OPERATIONS:
            self._require_run_of_workflow(grant, slots, token)
        if operation == "create_branch":
            self._require_branch_source(grant, slots, snapshot, token)
        # A merge is addressed only after the provider's own metadata confirms
        # the pull request targets the granted reference (N13).
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
        status, raw = self._exchange(operation, method, path, wire_body(snapshot),
                                     token)
        self._verify_response(operation, slots, raw)
        event_reason = "ok" if status < 300 else "http_" + str(status)
        # A URL path never enters the audit event: the operation and status
        # describe the call without naming a repository route.
        self._audit.append({"at": int(time.time()), "grant": grant.grant_id, "operation": operation,
                            "path_kind": "official_endpoint", "status": status,
                            "decision": "allow", "reason": event_reason})
        if status >= 300:
            raise ConnectorDenied("http_" + str(status))
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            raise ConnectorDenied("invalid_response")

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

        A grant names the account it was issued for, and only a credential can
        prove the account behind a token.  ``token`` is the snapshot this
        request read once: the same value is verified here and transmitted
        later, so a credential that was never verified cannot ride out (F07).
        The remembered identity is the verified **(token fingerprint,
        account)** pair, so a second grant naming a different account behind
        the same token is re-verified rather than accepted on the first one's
        word, and a configured-but-absent credential never passes the guard:
        there is nothing that could prove the account, so the request is
        refused.
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

    def _require_branch_source(self, grant: Grant, payload: Mapping[str, Any],
                               body: Mapping[str, Any], token: Optional[str]) -> None:
        """Bind a branch creation to the granted reference's own head (N08).

        A branch is created **from** the granted reference, so its source must
        be that reference's head as the provider reports it — trusted
        metadata, not the caller's claim — and the new branch's target must be
        a bounded ``refs/heads`` name rather than any other reference form.
        """
        reference = str(getattr(grant, "reference", "") or "")
        target = body.get("ref")
        if not isinstance(target, str) or len(target) > 128 \
                or any(ord(character) < 0x20 or ord(character) == 0x7F
                       for character in target):
            raise ConnectorDenied("unsafe_body_value")
        prefix = "refs/heads/"
        if not target.startswith(prefix):
            raise ConnectorDenied("unsafe_body_value")
        # the branch name is a single bounded, path-free segment: a traversing
        # or multi-segment target is not a branch name
        name = target[len(prefix):]
        if not name or len(name) > 64 or "/" in name or name in (".", "..") \
                or name.strip() != name:
            raise ConnectorDenied("unsafe_body_value")
        repository = self._repository(payload)
        self._charge_authorization_request()
        status, raw = self._exchange("get_reference_head", "GET",
                                     "/repos/{}/git/ref/heads/{}".format(repository,
                                                                         reference),
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
        declared = payload.get("sha")
        if declared is not None and str(declared) != head:
            raise ConnectorDenied("reference_not_granted")
        if str(body.get("sha", "")) != head:
            raise ConnectorDenied("reference_not_granted")

    def _authorization_context(self, grant: Grant, workflow: str, run_id: str,
                               token: Optional[str]) -> Tuple[str, ...]:
        """The complete context an ownership decision belongs to (N07).

        A verified run is evidence **for this grant, on this repository, under
        this reference, for this account, with this credential**: the cache key
        carries all of it, so an entry established under one context can never
        authorize the same run id under another.  The reference comes from the
        grant, never from the caller's slots.
        """
        return (self.name, str(getattr(grant, "repository", "")),
                str(getattr(grant, "reference", "")),
                str(getattr(grant, "account", "")),
                self._token_fingerprint(self.name, token) or "",
                workflow, run_id)

    def _require_run_of_workflow(self, grant: Grant, slots: Mapping[str, Any],
                                 token: Optional[str]) -> None:
        """Establish from trusted metadata that this run belongs to the grant.

        A caller-declared workflow name proves nothing about which run an id
        names: the run is addressed only after the workflow's **own runs list**
        - the official endpoint's answer, not the caller's claim - contains
        the requested id (N07).  Evidence is remembered per complete
        authorization context, for a bounded time, so a repeated operation on
        the same run does not re-query while a different context always does.
        Concurrent lookups of the same context are coalesced under the lock.
        Missing or malformed evidence refuses.
        """
        workflow = str(slots.get("workflow", ""))
        run_id = str(slots.get("run_id", ""))
        key = self._authorization_context(grant, workflow, run_id, token)
        stamp = time.time()
        with self._run_lock:
            verified_at = self._verified_runs.get(key)
            if verified_at is not None and stamp - verified_at < RUN_OWNERSHIP_TTL_SECONDS:
                return
            # The lookup runs under the lock, so a concurrent request for the
            # same context waits and then sees the entry rather than issuing a
            # duplicate authorization request (N06).
            self._charge_authorization_request()
            repository = self._repository(slots)
            status, raw = self._exchange(
                "list_workflow_runs", "GET",
                "/repos/{}/actions/workflows/{}/runs?per_page=100".format(repository,
                                                                         workflow),
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
            owned = {str(entry.get("id")) for entry in runs if isinstance(entry, dict)}
            if run_id not in owned:
                raise ConnectorDenied("run_not_of_workflow")
            self._verified_runs[key] = time.time()
            while len(self._verified_runs) > MAX_VERIFIED_RUNS:
                self._verified_runs.pop(next(iter(self._verified_runs)))

    def _require_merge_target(self, grant: Grant, slots: Mapping[str, Any],
                              token: Optional[str]) -> None:
        """Bind a merge to the pull request's own target reference (N13).

        A grant binds a repository and a reference, but a merge is addressed
        by a numeric id: without this check a pull request targeting another
        branch could be merged under a grant that never authorized it.  The
        destination is therefore read from trusted provider metadata - the
        pull request's own ``base`` - before any merge is issued.
        """
        repository = self._repository(slots)
        issue = str(slots.get("issue", ""))
        granted_reference = str(getattr(grant, "reference", "") or "")
        with self._run_lock:
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
        """Count one authorization request against the instance's bound (N06).

        A bounded cache bounds stored entries, not requests: a flood of identity
        mismatches or foreign runs would otherwise issue unbounded
        authorization traffic.  Returns nothing; refuses with a typed reason.
        """
        with self._call_lock:
            self._authorization_requests += 1
            if self._authorization_requests > MAX_AUTHORIZATION_REQUESTS:
                raise ConnectorDenied("authorization_traffic_exhausted")

    def _reserve_call(self, grant: Grant, operation: str) -> str:
        """Atomically verify the grant ceiling and reserve one call slot.

        The check and the increment share one lock, so a burst of concurrent
        calls cannot pass the ceiling together and discover only afterwards
        that it was exhausted.  This reserves a **repository operation**:
        identity and ownership verification are authorization traffic, bounded
        separately by ``_charge_authorization_request`` (N06).
        """
        with self._call_lock:
            allowed, reason = self.check(grant, operation)
            if not allowed:
                return reason
            self._calls[grant.grant_id] = self._calls.get(grant.grant_id, 0) + 1
            return ""

    # -- request paths (official endpoints only) -----------------------------
    @staticmethod
    def _verify_response(operation: str, payload: Mapping[str, Any], raw: bytes) -> None:
        """Verify response-level facts where the official API exposes them."""
        if operation != "read_file":
            return
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConnectorDenied("invalid_response")
        if not isinstance(data, dict):
            raise ConnectorDenied("invalid_response")
        reference = payload.get("reference")
        if reference is None:
            return
        ref_found = data.get("ref") or data.get("sha")
        if ref_found is not None and str(ref_found) != str(reference):
            raise ConnectorDenied("reference_mismatch")

    def _path_for(self, operation: str, payload: Mapping[str, Any]) -> str:
        repository = self._repository(payload)
        issue = str(payload.get("issue", ""))
        run_id = str(payload.get("run_id", ""))
        workflow = str(payload.get("workflow", ""))
        # The reference already passed the grant check: the query string uses
        # exactly that validated value.
        reference = str(payload.get("reference", payload.get("branch", "")))
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
        if reference and operation in ("read_file", "list_branches"):
            return paths[operation] + "?ref={}".format(reference)
        return paths.get(operation, "")

    # -- bounded HTTP --------------------------------------------------------
    def _account_request(self, timeout: float, token: Optional[str] = None) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport("GET", "/user", {})
        opener = urllib.request.build_opener(_NoRedirect)
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "tihulu-boru-core"}
        if token is None:
            token = self._token_value()
        if token:
            headers["Authorization"] = "Bearer " + token.strip()
        request = urllib.request.Request(self.base_url + "/user", method="GET", headers=headers)
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
    def _repository(payload) -> str:
        from .scope import RepositoryRef

        return RepositoryRef.parse(str(payload.get("repository", ""))).encoded()

    def _exchange(self, operation: str, method: str, path: str, body: Mapping[str, Any],
                  token: Optional[str] = None) -> Tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(method, path, body)
        if not self.base_url.lower().startswith("https://") and not self.allow_http_endpoints:
            raise ConnectorDenied("insecure_endpoint")
        headers = {"Accept": "application/vnd.github+json", "Content-Type": "application/json",
                   "User-Agent": "tihulu-boru-core"}
        if token is None:
            token = self._token_value()
        if token:
            headers["Authorization"] = "Bearer " + token.strip()
        request = urllib.request.Request(self.base_url + path, method=method,
                                         data=json.dumps(body).encode("utf-8") if body else None,
                                         headers=headers)
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=30) as response:
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                if content_type and content_type not in ("application/json", "text/plain"):
                    raise ConnectorDenied("unexpected_content_type")
                return response.status, response.read(512 * 1024)
        except urllib.error.HTTPError as error:
            # An error body is diagnostic, never a payload: keep a bounded
            # prefix, exactly as the account request does.
            body_bytes = _bounded_read(error, MAX_ERROR_BODY_BYTES)
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
