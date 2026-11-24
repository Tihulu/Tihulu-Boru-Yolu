"""Versioned repository-connector contracts (P8 source slice).

Connectors are **optional** surfaces. They cannot grant themselves rights:
every operation must match an explicit, owner-issued capability grant, and a
denied operation must not produce any outbound request. Model prompts,
Kandev/Langflow tasks and Langflow flow output are never an authorization
source (issue #8, #9).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple



class Capability(str, Enum):
    """Corresponds to the READ_ONLY / ISSUE_AND_REVIEW / REPO_WRITE tiers."""

    REPO_READ = "REPO_READ"
    ISSUE_WRITE = "ISSUE_WRITE"
    CODE_PR_WRITE = "CODE_PR_WRITE"
    ACTIONS_DISPATCH = "ACTIONS_DISPATCH"
    ACTIONS_ADMIN = "ACTIONS_ADMIN"
    MERGE_RELEASE = "MERGE_RELEASE"


#: Which operation each capability unlocks. A narrower tier never unlocks a
#: broader operation, even via another tier on the same account.
OPERATION_CAPABILITIES: Dict[str, Capability] = {
    "list_repositories": Capability.REPO_READ,
    "read_file": Capability.REPO_READ,
    "list_branches": Capability.REPO_READ,
    "get_commit": Capability.REPO_READ,
    "list_issues": Capability.REPO_READ,
    "get_pull": Capability.REPO_READ,
    "list_workflows": Capability.REPO_READ,
    "get_run": Capability.REPO_READ,
    "get_run_logs": Capability.REPO_READ,
    "get_artifacts": Capability.REPO_READ,
    "create_issue": Capability.ISSUE_WRITE,
    "comment_issue": Capability.ISSUE_WRITE,
    "update_issue": Capability.ISSUE_WRITE,
    "create_branch": Capability.CODE_PR_WRITE,
    "put_file": Capability.CODE_PR_WRITE,
    "create_pull": Capability.CODE_PR_WRITE,
    "review_pull": Capability.CODE_PR_WRITE,
    "dispatch_workflow": Capability.ACTIONS_DISPATCH,
    "rerun_workflow": Capability.ACTIONS_DISPATCH,
    "cancel_run": Capability.ACTIONS_DISPATCH,
    "configure_workflow": Capability.ACTIONS_ADMIN,
    "merge_pull": Capability.MERGE_RELEASE,
    "create_release": Capability.MERGE_RELEASE,
}

#: Operations that must never be reachable from a read-only profile.
WRITE_OPERATIONS = frozenset(name for name, cap in OPERATION_CAPABILITIES.items() if cap is not Capability.REPO_READ)


def _workflow_id(value: Any) -> str:
    """Bounded workflow identifier used by a grant's ``workflow_ids``."""
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("workflow id must be a bounded non-empty string")
    if any(character in value for character in ("?", "#", "\\", " ", "\t", "\n", "%", "@", ":", "&", "=")):
        raise ValueError("workflow id contains an unsafe character")
    if value.strip() != value or ".." in value.split("/"):
        raise ValueError("workflow id must not traverse")
    return value


@dataclass(frozen=True)
class Grant:
    """One owner-issued capability grant.

    A prompt can never create or widen a grant; only the owner can, and only
    for the bound account, repository, reference, workflow, operation set, call
    ceiling and expiry.
    """

    grant_id: str
    account: str
    repository: str
    reference: str
    operations: Tuple[str, ...]
    capabilities: Tuple[Capability, ...]
    max_calls: int
    issued_at: float
    expires_at: float
    disclosure_recipient: Optional[str] = None
    nonce: str = ""
    #: Workflow identifiers this grant may dispatch, configure or re-run.
    workflow_ids: Tuple[str, ...] = ()
    #: Owner-declared workflow input schema (a JSON object). When present, a
    #: dispatch body is validated against it before any transport. Optional,
    #: bounded, and owner-provided only: a payload never supplies it.
    input_declaration_json: str = ""

    def __post_init__(self) -> None:
        """Reject malformed grants at construction time."""
        errors = self.validate()
        if errors:
            raise ValueError("; ".join(errors))

    def validate(self) -> List[str]:
        errors: List[str] = []
        for name, limit in (("grant_id", 128), ("account", 128), ("repository", 256), ("reference", 256), ("nonce", 64)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(name + " must be a bounded non-empty string")
        if not isinstance(self.operations, tuple) or not self.operations:
            errors.append("operations must be a non-empty tuple")
        else:
            for operation in self.operations:
                if operation not in OPERATION_CAPABILITIES:
                    errors.append("unknown operation: " + str(operation))
        if not isinstance(self.capabilities, tuple) or not self.capabilities:
            errors.append("capabilities must be a non-empty tuple")
        else:
            for capability in self.capabilities:
                if not isinstance(capability, Capability):
                    errors.append("unknown capability")
        for name in ("max_calls",):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
                errors.append(name + " must be 1..10000")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            # A nonfinite timestamp makes every expiry comparison false, so the
            # grant would never expire: refuse it at construction.
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value <= 0:
                errors.append(name + " must be a finite positive timestamp")
        if isinstance(self.issued_at, (int, float)) and isinstance(self.expires_at, (int, float)) \
                and self.expires_at <= self.issued_at:
            errors.append("expires_at must follow issued_at")
        for workflow_id in self.workflow_ids:
            try:
                _workflow_id(workflow_id)
            except ValueError:
                errors.append("workflow_ids must be bounded non-empty names")
        if len(set(self.workflow_ids)) != len(self.workflow_ids):
            errors.append("duplicate workflow ids")
        if self.input_declaration_json:
            if not isinstance(self.input_declaration_json, str) or len(self.input_declaration_json) > 16 * 1024:
                errors.append("input_declaration_json must be a bounded string")
            else:
                try:
                    declared = json.loads(self.input_declaration_json)
                except (TypeError, ValueError):
                    errors.append("input_declaration_json must be a JSON object")
                else:
                    if not isinstance(declared, Mapping) or len(declared) > 16:
                        errors.append("input_declaration_json must declare at most 16 inputs")
                    else:
                        for key, spec in declared.items():
                            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                                errors.append("input_declaration_json keys must be bounded names")
                            elif not isinstance(spec, Mapping) or spec.get("type") not in (
                                    "string", "boolean", "choice", "number", "environment"):
                                errors.append("input_declaration_json specs must be typed")
        if self.disclosure_recipient is not None and (
            not isinstance(self.disclosure_recipient, str) or len(self.disclosure_recipient) > 128
        ):
            errors.append("disclosure_recipient must be a bounded string")
        return errors

    def declared_inputs(self) -> Optional[Dict[str, Any]]:
        """The owner-declared input schema, or ``None`` when none was issued."""
        if not self.input_declaration_json:
            return None
        try:
            declared = json.loads(self.input_declaration_json)
        except (TypeError, ValueError):  # pragma: no cover - validated at construction
            return None
        return dict(declared) if isinstance(declared, Mapping) else None

    def permits(self, operation: str, now: float, calls_used: int) -> Tuple[bool, str]:
        if operation not in self.operations:
            return False, "operation_not_granted"
        required = OPERATION_CAPABILITIES[operation]
        if required not in self.capabilities:
            return False, "capability_not_granted"
        # The grant is valid only between its own bounds: a future-issued grant
        # is not usable just because it has not expired yet (N09).
        if now < self.issued_at:
            return False, "grant_not_yet_valid"
        if now >= self.expires_at:
            return False, "grant_expired"
        if calls_used >= self.max_calls:
            return False, "grant_exhausted"
        return True, ""


class RepositoryProvider:
    """Interface every optional repository connector implements."""

    name = "provider"

    def capabilities(self) -> Tuple[Capability, ...]:  # pragma: no cover - interface
        raise NotImplementedError
