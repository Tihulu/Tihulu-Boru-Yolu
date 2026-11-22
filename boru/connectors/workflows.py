"""Workflow discovery and dispatch-input validation (issue #9, P8 source slice).

Implements the read-only contract and the dispatch guard: a workflow is listed
from the official endpoint and its declared inputs can be read, and
``boru.connectors.scope.check_dispatch_body`` validates a ``workflow_dispatch``
body **before** any dispatch call — the granted reference exactly, bounded
input keys and values, and, when the owner supplies the declaration, the
inputs against that declaration.

The declaration is owner-provided. The repository does not read a workflow
file's input schema for the caller, so a dispatch without a declaration keeps
the bounded shape check only; closing that last step (read the file, then
dispatch) is recorded as a pilot-gate task rather than implied here. Nothing in
this module opens a listener, dispatches by itself, or reads secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..errors import ConnectorDenied

#: ``workflow_dispatch`` input types the GitHub API declares.
INPUT_TYPES = ("string", "boolean", "choice", "number", "environment")
MAX_INPUTS = 16
MAX_VALUE_CHARS = 512


@dataclass(frozen=True)
class WorkflowSummary:
    """One workflow as the official endpoint reports it."""

    workflow_id: str
    name: str
    path: str
    state: str = "unknown"
    supports_dispatch: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.workflow_id, str) or not self.workflow_id.strip():
            errors.append("workflow_id must be a bounded non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            errors.append("name must be a bounded non-empty string")
        if not isinstance(self.path, str) or not self.path.strip():
            errors.append("path must be a bounded non-empty string")
        if not isinstance(self.state, str) or not self.state.strip():
            errors.append("state must be a bounded non-empty string")
        if not isinstance(self.supports_dispatch, bool):
            errors.append("supports_dispatch must be a boolean")
        return errors


def parse_workflows(payload: Any) -> List[WorkflowSummary]:
    """Parse the official actions/workflows response into typed summaries."""
    if not isinstance(payload, dict):
        raise ConnectorDenied("invalid_response")
    workflows = payload.get("workflows")
    if not isinstance(workflows, list):
        raise ConnectorDenied("invalid_response")
    parsed: List[WorkflowSummary] = []
    for entry in workflows[:64]:
        if not isinstance(entry, dict):
            raise ConnectorDenied("invalid_response")
        workflow_id = entry.get("id")
        name = entry.get("name")
        path = entry.get("path")
        state = entry.get("state", "unknown")
        if not isinstance(workflow_id, (int, str)) or isinstance(workflow_id, bool):
            raise ConnectorDenied("invalid_response")
        summary = WorkflowSummary(
            workflow_id=str(workflow_id),
            name=str(name or ""),
            path=str(path or ""),
            state=str(state),
            supports_dispatch=bool(entry.get("supports_dispatch", False)),
        )
        if summary.validate():
            raise ConnectorDenied("invalid_response")
        parsed.append(summary)
    return parsed


def validate_dispatch_inputs(declared: Optional[Mapping[str, Any]],
                             provided: Optional[Mapping[str, Any]]) -> Tuple[bool, str]:
    """Validate dispatch inputs against the workflow's declaration.

    The declaration is what the workflow file exposes; Boru refuses a dispatch
    whose inputs are unknown, mistyped, out of range or oversized, and refuses a
    required input that is missing.
    """
    if provided is None:
        provided = {}
    if not isinstance(provided, Mapping):
        return False, "inputs_malformed"
    if len(provided) > MAX_INPUTS:
        return False, "inputs_too_many"
    for key, value in provided.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            return False, "inputs_malformed"
        if isinstance(value, (Mapping, list)):
            return False, "inputs_malformed"
        if isinstance(value, str):
            if len(value) > MAX_VALUE_CHARS or any(c in value for c in ("\n", "\r", "\x00")):
                return False, "inputs_malformed"
    if declared is None:
        # No declaration available: refuse rather than guessing a schema.
        return False, "inputs_undeclared"
    if not isinstance(declared, Mapping):
        return False, "inputs_malformed"
    for key in provided:
        spec = declared.get(key)
        if spec is None:
            return False, "input_not_declared"
        if not isinstance(spec, Mapping):
            return False, "inputs_malformed"
        kind = spec.get("type")
        if kind not in INPUT_TYPES:
            return False, "input_type_unknown"
        value = provided[key]
        if kind == "boolean" and not isinstance(value, bool):
            return False, "input_type_mismatch"
        if kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False, "input_type_mismatch"
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                return False, "input_out_of_range"
            if isinstance(maximum, (int, float)) and value > maximum:
                return False, "input_out_of_range"
        if kind == "choice":
            options = spec.get("options")
            if isinstance(options, list) and value not in options:
                return False, "input_out_of_range"
        if kind in ("string", "environment") and not isinstance(value, str):
            return False, "input_type_mismatch"
    for key, spec in declared.items():
        if isinstance(spec, Mapping) and spec.get("required") is True and key not in provided:
            return False, "required_input_missing"
    return True, ""
