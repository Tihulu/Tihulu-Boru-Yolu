"""Fail-closed request scoping shared by GitHub and GitLab connectors.

This is an application-level authorization check, not an OS security
boundary or proof of the remote token identity. The caller may request
only a typed operation on the grant-bound repository/reference. Direct
HTTP method/path overrides are never an authorization mechanism.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from ..errors import ConnectorDenied
from .base import Grant

# Strings used in URL path/query slots must never inject a new URL component.
# Keep unusual names denied until an explicit percent-encoded typed API exists.
_PARAM_KEYS = frozenset({"repository", "path", "issue", "run_id", "workflow",
                         "sha", "branch", "ref", "reference"})


def _safe_segment(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return False
    item = str(value)
    if not item or len(item) > 512:
        return False
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in item):
        return False
    if any(ch in item for ch in ("?", "#", "%", "\\", ":", "@")):
        return False
    return all(section not in ("", ".", "..") for section in item.split("/"))


def validate_request_scope(
    grant: Grant,
    operation: str,
    payload: Optional[Mapping[str, Any]],
    body: Optional[Mapping[str, Any]],
    method: Optional[str],
    path: str,
) -> Mapping[str, Any]:
    """Validate before transport, returning only the original typed payload.

    No network request may occur on denial. No secret or private input is
    interpolated into an exception.
    """
    if method is not None or path:
        raise ConnectorDenied("custom_request_forbidden")
    if payload is not None and not isinstance(payload, Mapping):
        raise ConnectorDenied("invalid_payload")
    if body is not None and not isinstance(body, Mapping):
        raise ConnectorDenied("invalid_payload")
    params = payload if payload is not None else {}
    request_body = body if body is not None else {}

    if operation == "list_repositories":
        # Listing is account-wide; this cannot prove the bound account's
        # identity. It must remain independently gated by token permissions.
        if "repository" in params and params["repository"] != grant.repository:
            raise ConnectorDenied("repository_not_granted")
    elif params.get("repository") != grant.repository:
        raise ConnectorDenied("repository_not_granted")

    for values in (params, request_body):
        if "repository" in values and values["repository"] != grant.repository:
            raise ConnectorDenied("repository_not_granted")
        for key in ("ref", "reference", "branch"):
            if key in values and values[key] != grant.reference:
                raise ConnectorDenied("reference_not_granted")
    # A read_file call without an explicit branch would silently select
    # the server default branch, not necessarily the bound grant reference.
    if operation == "read_file" and "branch" not in params:
        raise ConnectorDenied("reference_required")

    for key in _PARAM_KEYS:
        if key in params and not _safe_segment(params[key]):
            raise ConnectorDenied("invalid_parameter")
    return params
