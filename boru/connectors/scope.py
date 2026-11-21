"""Request-scope hardening for repository connectors (issue #15).

A grant that authorizes an operation on **one repository and reference** must not
be usable to reach another repository, another reference or a hand-built URL.
Two bypasses are closed here, before any transport is constructed:

1. **Binding:** the repository/branch in the request must match the grant's
   repository and reference (after percent-encoding comparison).
2. **No raw overrides:** an explicit `path` override is refused, and a `method`
   override is refused unless the operation defines it.

Additionally, path slots are checked for characters that would escape the
intended URL (control characters, spaces, `..`, `%`, `?`, `#`, backslashes and
userinfo), and an implicit default-branch file read is refused so the reference
must be explicit.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from ..errors import ConnectorDenied

#: Characters that must not appear inside any slot (URL-escape or control risk).
FORBIDDEN_CHARS = ("?", "#", "\\", " ", "\t", "\n", "\r", "%", "@", ":", "&", "=", "\"")

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
               path: Optional[str], default_method: Optional[str]) -> None:
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
    if workflow is not None:
        _slot(workflow, "workflow", 256, allow_slash=True)
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
