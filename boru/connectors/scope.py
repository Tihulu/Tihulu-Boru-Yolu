"""Request-scope hardening for repository connectors (issue #15).

A grant that authorizes an operation on **one repository and reference** must not
be usable to reach another repository, another reference or a hand-built URL.
Two bypasses are closed here, before any transport is constructed:

1. **Binding:** the repository/branch in the request must match the grant's
   repository and reference (after percent-encoding comparison).
2. **No raw overrides:** an explicit `path` override is refused, and a `method`
   override is refused unless the operation defines it.

Additionally, path slots are checked for characters that would escape the
intended URL (control characters including NUL, spaces, `..`, `%`, `?`, `#`,
backslashes and userinfo), and an implicit default-branch file read is refused
so the reference must be explicit.

The check also returns the **validated slots** the caller must use to build the
request, so the value that was checked is the value that reaches the endpoint:
there is no second parse and no second interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from ..errors import ConnectorDenied

#: Characters that must not appear inside any slot (URL-escape or control risk).
FORBIDDEN_CHARS = ("?", "#", "\\", " ", "\t", "\n", "\r", "%", "@", ":", "&", "=", "\"")

#: Dispatch bodies are bounded: the granted reference and small typed inputs.
MAX_BODY_KEYS = 10
MAX_BODY_VALUE_CHARS = 512


def _check_control(value: str, label: str) -> None:
    """Reject every control character, including NUL, inside a slot."""
    for character in value:
        if ord(character) < 0x20 or ord(character) == 0x7F:
            raise ConnectorDenied("unsafe_" + label)

#: Characters that must not appear inside a reference/branch/slot-without-slash.
FORBIDDEN_SLASH_CHARS = FORBIDDEN_CHARS + ("/",)


def _check_chars(value: str, forbidden: Sequence[str], label: str) -> None:
    for character in forbidden:
        if character in value:
            raise ConnectorDenied("unsafe_" + label)


def _check_segments(value: str, label: str) -> None:
    """Reject empty, relative or parent segments in a slash-separated slot."""
    for part in value.split("/"):
        if not part or part in (".", "..") or part.strip() != part:
            raise ConnectorDenied("unsafe_" + label)


def _slot(value: Any, label: str, limit: int = 256, *, allow_slash: bool = False) -> str:
    """Validate one URL slot and return its unencoded form."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ConnectorDenied("invalid_" + label)
    if value.strip() != value:
        raise ConnectorDenied("unsafe_" + label)
    forbidden = FORBIDDEN_CHARS if allow_slash else FORBIDDEN_SLASH_CHARS
    _check_chars(value, forbidden, label)
    _check_control(value, label)
    _check_segments(value, label)
    return value


#: Operations whose repository slot must match the grant repository.
REPO_SCOPED = {
    "read_file", "list_branches", "get_commit", "list_issues", "create_issue",
    "comment_issue", "update_issue", "get_pull", "create_branch", "put_file",
    "create_pull", "review_pull", "merge_pull", "list_workflows", "dispatch_workflow",
    "rerun_workflow", "cancel_run", "get_run", "get_run_logs", "get_artifacts",
    "configure_workflow", "create_release",
}

#: Operations that are account-wide and need a separate account-scoped design.
ACCOUNT_SCOPED = {"list_repositories"}

#: Operations addressed by a workflow name, and by a run that belongs to one.
#: A run id alone is never sufficient: the granted workflow is what scopes it.
WORKFLOW_OPERATIONS = {
    "dispatch_workflow", "rerun_workflow", "cancel_run", "configure_workflow",
    "get_run", "get_run_logs", "get_artifacts",
}

#: N08/N11: per-provider, per-operation write-body contracts.  Each entry maps
#: an operation to (the only keys its body may carry, the keys that are
#: **mandatory and must equal the granted reference**).  A reference key is
#: required, not merely checked when present: omitting it would let the remote
#: API apply its own default-branch behaviour, which is the divergence N08
#: describes.  Each provider has its own table because the official endpoints
#: use different field names (GitHub ``head``/``base`` versus GitLab
#: ``source_branch``/``target_branch``) — one shared table refused legitimate
#: GitLab requests (N11).
GITHUB_WRITE_BODY_CONTRACTS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "create_issue": (("title", "body", "labels", "assignees", "milestone"), ()),
    "comment_issue": (("body",), ()),
    "update_issue": (("title", "body", "state", "labels", "assignees", "milestone"), ()),
    "create_branch": (("ref", "sha"), ()),
    "put_file": (("message", "content", "branch", "sha", "committer", "author"), ("branch",)),
    "create_pull": (("title", "head", "base", "body", "draft", "maintainer_can_modify"),
                    ("base",)),
    "review_pull": (("body", "event", "comments"), ()),
    "merge_pull": (("commit_title", "commit_message", "sha", "merge_method"), ()),
    "dispatch_workflow": (("ref", "inputs"), ("ref",)),
    "rerun_workflow": ((), ()),
    "cancel_run": ((), ()),
    "configure_workflow": ((), ()),
    "create_release": (("tag_name", "target_commitish", "name", "body", "draft", "prerelease"),
                       ("target_commitish",)),
}

#: GitLab's official request shapes: merge requests use ``source_branch`` and
#: ``target_branch``, a branch is created from a ``ref``, and a release targets
#: a ``ref``.  The mandatory column is the destination reference each write
#: must name, exactly as the grant authorizes it.
GITLAB_WRITE_BODY_CONTRACTS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "create_issue": (("title", "description", "labels", "assignee_ids", "milestone_id"), ()),
    "comment_issue": (("body",), ()),
    "update_issue": (("title", "description", "state_event", "labels", "assignee_ids",
                      "milestone_id"), ()),
    "create_branch": (("branch", "ref"), ("ref",)),
    "put_file": (("branch", "content", "encoding", "commit_message"), ("branch",)),
    "create_pull": (("title", "source_branch", "target_branch", "description",
                     "remove_source_branch", "squash"), ("target_branch",)),
    "review_pull": (("body",), ()),
    "merge_pull": (("merge_request_message", "squash", "squash_commit_message"), ()),
    "dispatch_workflow": (("ref", "inputs"), ("ref",)),
    "rerun_workflow": ((), ()),
    "cancel_run": ((), ()),
    "configure_workflow": ((), ()),
    "create_release": (("tag_name", "ref", "name", "description", "assets"),
                       ("ref",)),
}

#: Kept for callers that want one provider's table by name.
WRITE_BODY_CONTRACTS = GITHUB_WRITE_BODY_CONTRACTS

#: Body values are bounded: a body is a small typed document, never a payload.
MAX_BODY_DEPTH = 2
MAX_BODY_KEYS = 16
MAX_BODY_VALUE_CHARS = 512
MAX_BODY_ITEMS = 16


@dataclass(frozen=True)
class RepositoryRef:
    """Typed repository name: exactly two encoded segments, no traversal."""

    owner: str
    name: str

    @classmethod
    def parse(cls, value: str) -> "RepositoryRef":
        slot = _slot(value, "repository", 256, allow_slash=True)
        if slot.count("/") != 1:
            raise ConnectorDenied("unsafe_repository")
        owner, name = slot.split("/", 1)
        return cls(owner=owner, name=name)

    def segments(self) -> Tuple[str, str]:
        """Percent-encode each segment for the official path (issue #15 gap)."""
        from urllib.parse import quote

        return quote(self.owner, safe=""), quote(self.name, safe="")

    def encoded(self) -> str:
        """Slash-separated form, e.g. GitHub's ``/repos/{owner}/{repo}``."""
        return "{}/{}".format(*self.segments())

    def percent_encoded(self) -> str:
        """``%2F``-separated form, e.g. GitLab's project path."""
        return "%2F".join(self.segments())

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "{}/{}".format(self.owner, self.name)


def repository_matches(requested: str, granted: str) -> bool:
    """Compare repository identifiers by their percent-encoded components."""
    if requested == granted:
        return True
    return _decode(requested) == _decode(granted)


def _decode(value: str) -> str:
    try:
        from urllib.parse import unquote

        return unquote(value)
    except Exception:  # pragma: no cover - defensive
        return value


def check_call(grant: Any, operation: str, payload: Mapping[str, Any], *, method: Optional[str],
               path: Optional[str], default_method: Optional[str]) -> Dict[str, str]:
    """Raise ``ConnectorDenied`` if this call is not exactly the granted one.

    Called by every provider immediately before an official endpoint URL is
    constructed, so a denial produces no outbound request.
    """
    if path:
        raise ConnectorDenied("path_override_refused")
    if method is not None and default_method is not None and method != default_method:
        raise ConnectorDenied("method_override_refused")
    if any(character.isspace() for character in str(default_method or "")):
        raise ConnectorDenied("invalid_method")
    payload = payload or {}
    if operation in REPO_SCOPED:
        repository = _slot(payload.get("repository"), "repository", 256, allow_slash=True)
        if repository.count("/") != 1:
            raise ConnectorDenied("unsafe_repository")
        if not repository_matches(repository, getattr(grant, "repository", "")):
            raise ConnectorDenied("repository_not_granted")
    elif operation in ACCOUNT_SCOPED:
        # An account-wide listing is a distinct capability: a repository-scoped
        # grant never reaches it.
        raise ConnectorDenied("account_scope_not_granted")
    else:
        raise ConnectorDenied("operation_not_scoped")
    # A file/contents read must name its reference explicitly.
    reference = payload.get("reference", payload.get("branch"))
    if operation in ("read_file", "put_file") and reference is None:
        raise ConnectorDenied("reference_required")
    if reference is not None:
        reference = _slot(str(reference), "reference", 256)
        granted_reference = _slot(str(getattr(grant, "reference", "") or ""), "reference", 256)
        if reference != granted_reference:
            raise ConnectorDenied("reference_not_granted")
    file_path = payload.get("path")
    if file_path is not None:
        _slot(file_path, "path", 512, allow_slash=True)
    issue = payload.get("issue")
    if issue is not None:
        _slot(str(issue), "issue", 32)
        if not str(issue).isdigit():
            raise ConnectorDenied("unsafe_issue")
    run_id = payload.get("run_id")
    if run_id is not None:
        _slot(str(run_id), "run_id", 32)
        if not str(run_id).isdigit():
            raise ConnectorDenied("unsafe_run_id")
    workflow = payload.get("workflow")
    # A run belongs to a workflow: without a granted workflow name the
    # operation cannot be scoped, so it is refused rather than guessed.  This
    # holds for every workflow-addressed operation, the run operations
    # included: a run id alone names nothing the grant authorized, so the run
    # metadata is bound to the granted workflow here rather than by the
    # endpoint's own lookup (N07).
    if workflow is not None or operation in WORKFLOW_OPERATIONS:
        if workflow is None:
            raise ConnectorDenied("workflow_required")
        workflow = _slot(workflow, "workflow", 256, allow_slash=True)
        allowed_workflows = getattr(grant, "workflow_ids", ()) or ()
        if not allowed_workflows or workflow not in allowed_workflows:
            raise ConnectorDenied("workflow_not_granted")
    sha = payload.get("sha")
    if sha is not None:
        _slot(sha, "sha", 64)
        if any(c not in "0123456789abcdef" for c in str(sha)):
            raise ConnectorDenied("unsafe_sha")
    # Grant fields must themselves be bounded.
    for name in ("grant_id", "repository", "reference"):
        value = getattr(grant, name, None)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ConnectorDenied("grant_" + name + "_invalid")
    return validated_slots(payload)


def validated_slots(payload: Mapping[str, Any]) -> Dict[str, str]:
    """Return the checked slot values a caller must use to build the request.

    Every provider builds its official path from this mapping, so a value that
    passes the check is the value that reaches the transport.
    """
    payload = payload or {}
    slots: Dict[str, str] = {}
    repository = payload.get("repository")
    if repository is not None:
        slots["repository"] = _slot(repository, "repository", 256, allow_slash=True)
    reference = payload.get("reference", payload.get("branch"))
    if reference is not None:
        slots["reference"] = _slot(str(reference), "reference", 256)
    for name, limit, digits in (("issue", 32, True), ("run_id", 32, True),
                                ("workflow", 256, False), ("sha", 64, False)):
        value = payload.get(name)
        if value is None:
            continue
        text = _slot(str(value), name, limit, allow_slash=name == "workflow")
        if digits and not text.isdigit():
            raise ConnectorDenied("unsafe_" + name)
        slots[name] = text
    file_path = payload.get("path")
    if file_path is not None:
        slots["path"] = _slot(file_path, "path", 512, allow_slash=True)
    return slots


def check_dispatch_body(grant: Any, body: Optional[Mapping[str, Any]],
                         declared: Optional[Mapping[str, Any]] = None) -> None:
    """Validate a workflow dispatch body before any transport is built.

    The body's ``ref`` must be exactly the granted reference (a payload can
    never widen it) and its ``inputs`` must be a bounded object of bounded
    values, so no unbounded or structured payload reaches the endpoint.

    The inputs are validated against the workflow's **declared input schema**,
    which travels with the grant (``Grant.input_declaration_json``) or is passed
    by the owner explicitly.  A non-empty input set without a declaration is
    refused: an input is a value the workflow reads, and shape alone cannot
    say which values it accepts.  The declaration is owner-provided — never
    read from the request payload — so a caller cannot grant itself a schema.
    """
    if body is None:
        raise ConnectorDenied("body_required")
    if not isinstance(body, Mapping):
        raise ConnectorDenied("invalid_body")
    if len(body) > MAX_BODY_KEYS:
        raise ConnectorDenied("body_too_large")
    # Only the dispatch body's documented keys may travel: an extra key is a
    # payload smuggled toward the endpoint (and a body cannot carry the schema
    # it is checked against).
    unknown = sorted(set(body) - {"ref", "inputs"})
    if unknown:
        raise ConnectorDenied("body_unknown_key")
    reference = body.get("ref")
    if reference is None:
        raise ConnectorDenied("reference_required")
    if str(reference) != str(getattr(grant, "reference", "") or ""):
        raise ConnectorDenied("reference_not_granted")
    inputs = body.get("inputs") or {}
    if not isinstance(inputs, Mapping):
        raise ConnectorDenied("invalid_body")
    if len(inputs) > MAX_BODY_KEYS:
        raise ConnectorDenied("body_too_large")
    if declared is None and hasattr(grant, "declared_inputs"):
        # The owner-declared schema travels with the grant, never with the body.
        declared = grant.declared_inputs()
    if inputs and declared is None:
        # Without the owner-supplied declaration there is no schema to validate
        # against, so a non-empty input set is refused rather than accepted on
        # shape alone: an input is a value the workflow will read.
        raise ConnectorDenied("inputs_undeclared")
    if declared is not None:
        from .workflows import validate_dispatch_inputs

        allowed, reason = validate_dispatch_inputs(declared, inputs)
        if not allowed:
            raise ConnectorDenied(reason)
    for key, value in inputs.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            raise ConnectorDenied("unsafe_body_key")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ConnectorDenied("unsafe_body_value")
        if isinstance(value, str):
            _check_control(value, "body_value")
            if len(value) > MAX_BODY_VALUE_CHARS:
                raise ConnectorDenied("body_too_large")


def _check_body_value(value: Any, label: str, depth: int = 0) -> None:
    """Reject an unbounded, structured or control-carrying body value."""
    if depth > MAX_BODY_DEPTH:
        raise ConnectorDenied("body_nested_too_deeply")
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if not -(2 ** 53) <= value <= 2 ** 53:
            raise ConnectorDenied("body_value_out_of_range")
        return
    if isinstance(value, str):
        if len(value) > MAX_BODY_VALUE_CHARS:
            raise ConnectorDenied("body_value_too_large")
        _check_control(value, "body_value")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_BODY_KEYS:
            raise ConnectorDenied("body_too_large")
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                raise ConnectorDenied("unsafe_body_key")
            _check_body_value(item, label, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_BODY_ITEMS:
            raise ConnectorDenied("body_too_large")
        for item in value:
            _check_body_value(item, label, depth + 1)
        return
    raise ConnectorDenied("unsafe_body_value")


def check_write_body(grant: Any, operation: str, body: Any,
                     payload: Optional[Mapping[str, Any]] = None,
                     contracts: Optional[Mapping[str, Tuple[Tuple[str, ...], Tuple[str, ...]]]] = None) -> None:
    """Validate a write body against its operation contract (N08/N11).

    ``check_call`` validates the request's **slots** and
    ``check_dispatch_body`` validates a dispatch body; every other write
    operation used to transmit its body unchecked, so the reference that was
    validated could diverge from the reference the body carried.  Each
    provider now has a typed contract per operation: the only keys it may
    carry, and the reference keys that are **mandatory** and must equal the
    granted reference.  The dispatch body itself stays with
    ``check_dispatch_body``, which additionally enforces its owner-declared
    input schema.

    ``contracts`` selects the provider's table.  It defaults to the GitHub
    table only so an older caller keeps the GitHub behaviour; both shipped
    connectors pass their own table explicitly.

    Operation-specific **provider** rules stay with the provider: GitHub's
    branch creation (a bounded ``refs/heads`` target and a source sha taken
    from the reference's own head) and GitLab's branch and merge-request
    field names are checked by each connector against its own endpoint, so a
    shared table can neither weaken nor misapply them.
    """
    if operation == "dispatch_workflow":
        # The dispatch body has its own schema-binding check.
        check_dispatch_body(grant, body or {})
        return
    table = contracts if contracts is not None else GITHUB_WRITE_BODY_CONTRACTS
    contract = table.get(operation)
    if contract is None:
        # Not a recognized write operation: nothing to check here.
        return
    allowed_keys, reference_keys = contract
    if body is None:
        # A mandatory reference key cannot be absent: an absent one lets the
        # remote API choose its own default branch, which is the divergence
        # this contract exists to close.
        if reference_keys:
            raise ConnectorDenied("reference_required_in_body")
        return
    if not isinstance(body, Mapping):
        raise ConnectorDenied("invalid_body")
    if len(body) > MAX_BODY_KEYS:
        raise ConnectorDenied("body_too_large")
    unknown = sorted(set(body) - set(allowed_keys))
    if unknown:
        raise ConnectorDenied("body_unknown_key")
    for key, value in body.items():
        _check_body_value(value, key)
    granted_reference = str(getattr(grant, "reference", "") or "")
    for key in reference_keys:
        if key not in body:
            raise ConnectorDenied("reference_required_in_body")
        if str(body[key]) != granted_reference:
            raise ConnectorDenied("reference_not_granted")
