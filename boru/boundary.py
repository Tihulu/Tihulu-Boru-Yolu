"""Cross-boundary tracer (issue #9): unclassified requests are refused.

The unsafe default in most agents is "allow when nobody checked". Boru Core
takes the opposite default: an outbound call must carry an explicit, registered
classification *before* it can leave the process, and a mismatch is a denial.

Classifications are per task, per recipient, per boundary and per data class.
A request that has no classification, that names a different recipient or
boundary than the one declared, that carries a data class higher than declared,
or that omits its grant reference, is refused without any network call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .errors import PolicyViolation

#: The widest data class: used when a payload cannot be classified at all.
WIDEST_DATA_CLASS = "L2"

BOUNDARIES: Tuple[str, ...] = ("model_inference", "repository_api", "local_worker", "local_disk")
DATA_CLASSES: Tuple[str, ...] = ("none", "L0", "L1", "L2")
_RANK = {value: index for index, value in enumerate(DATA_CLASSES)}
RECIPIENTS: Tuple[str, ...] = ("local", "cloud", "repository", "worker")


@dataclass(frozen=True)
class Classification:
    """What the owner declared about one outbound direction."""

    boundary: str
    recipient: str
    data_class: str = "none"
    grant_ref: Optional[str] = None

    def validate(self) -> list:
        errors = []
        if self.boundary not in BOUNDARIES:
            errors.append("unknown boundary")
        if self.recipient not in RECIPIENTS:
            errors.append("unknown recipient")
        if self.data_class not in DATA_CLASSES:
            errors.append("unknown data class")
        if self.data_class != "none" and not self.grant_ref:
            errors.append("a data-carrying classification needs a grant reference")
        if self.data_class == "L2" and self.recipient != "cloud":
            errors.append("L2 disclosure is only defined for a cloud recipient")
        return errors


class CrossBoundaryGuard:
    """Fail-closed registry of declared classifications."""

    def __init__(self) -> None:
        self._declared: Dict[Tuple[str, str, str], Classification] = {}
        self._used: Dict[str, int] = {}

    def declare(self, task_id: str, classification: Classification) -> None:
        _bounded(task_id)
        errors = classification.validate()
        if errors:
            raise PolicyViolation("; ".join(sorted(set(errors))))
        key = (task_id, classification.recipient, classification.boundary)
        if key in self._declared:
            raise PolicyViolation("classification already declared for this direction")
        self._declared[key] = classification

    def check(self, task_id: str, *, recipient: str, boundary: str,
              data_class: str = "none", grant_ref: Optional[str] = None) -> Tuple[bool, str]:
        try:
            _bounded(task_id)
        except PolicyViolation:
            return False, "malformed_request"
        if grant_ref is not None:
            try:
                _bounded(grant_ref)
            except PolicyViolation:
                return False, "malformed_request"
        if data_class not in DATA_CLASSES:
            return False, "unknown_data_class"
        key = (task_id, recipient, boundary)
        declared = self._declared.get(key)
        if declared is None:
            return False, "unclassified_request"
        if _RANK[data_class] > _RANK[declared.data_class]:
            return False, "data_class_not_declared"
        if declared.data_class != "none" and declared.grant_ref is None:
            return False, "grant_missing"
        if declared.data_class != "none" and data_class != "none" and grant_ref != declared.grant_ref:
            return False, "grant_mismatch"
        self._used[task_id] = self._used.get(task_id, 0) + 1
        return True, ""

    def declared_for(self, task_id: str) -> Dict[str, Classification]:
        _bounded(task_id)
        return {key[1] + "/" + key[2]: value for key, value in self._declared.items()
                if key[0] == task_id}

    def uses(self, task_id: str) -> int:
        _bounded(task_id)
        return self._used.get(task_id, 0)


def classify_payload(messages: Any) -> str:
    """Derive the data class of the actual outbound payload.

    A caller never states what crosses a boundary: the payload is classified
    from its content.  An empty payload carries nothing; any real content is
    at least ``L0``; a payload that is not bounded text cannot be classified
    and is treated as the widest class, so it is refused unless declared.
    """
    if not isinstance(messages, (list, tuple)):
        return "L2"
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            return "L2"
        if content.strip():
            return "L0"
    return "none"


def _bounded(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise PolicyViolation("task identifier must be a bounded non-empty string")
    return value
