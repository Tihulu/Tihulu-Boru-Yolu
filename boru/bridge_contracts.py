"""Offline bridge metadata contracts; never authenticate or execute a task.

This module is a candidate for issue #17, not a transport or grant boundary.
The caller must obtain identity, delegation history and grants from trusted
local state. Peer-supplied metadata is not authorization.
"""
from dataclasses import dataclass
import re

from .errors import ContractError, PolicyViolation

VERSION = 1
MAX_HOPS = 6
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", re.ASCII)
OPERATIONS = frozenset({
    "capabilities", "health", "submit", "status", "events",
    "cancel", "pause", "resume", "result", "request_review",
})


def _identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ContractError("invalid bridge identifier")
    return value


def _version(value):
    if type(value) is not int or value != VERSION:
        raise ContractError("unsupported bridge schema")


def _exact_dict(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ContractError("invalid bridge fields")


@dataclass(frozen=True)
class EngineManifest:
    engine_id: str
    operations: tuple
    schema_version: int = VERSION

    def __post_init__(self):
        _identifier(self.engine_id)
        _version(self.schema_version)
        if type(self.operations) is not tuple or not 1 <= len(self.operations) <= len(OPERATIONS):
            raise ContractError("invalid capability count")
        for operation in self.operations:
            if type(operation) is not str or operation not in OPERATIONS:
                raise ContractError("unsupported bridge operation")
        if len(set(self.operations)) != len(self.operations):
            raise ContractError("duplicate bridge operation")

    @classmethod
    def from_dict(cls, value):
        _exact_dict(value, {"engine_id", "operations", "schema_version"})
        operations = value["operations"]
        if type(operations) is not list or not 1 <= len(operations) <= len(OPERATIONS):
            raise ContractError("invalid capability count")
        return cls(value["engine_id"], tuple(operations), value["schema_version"])

    def as_dict(self):
        return {"engine_id": self.engine_id, "operations": list(self.operations),
                "schema_version": self.schema_version}


@dataclass(frozen=True)
class DelegationRoute:
    """Trusted-local routing metadata for one task; no permission is conveyed."""

    task_id: str
    owner_id: str
    visited: tuple
    hop_limit: int = MAX_HOPS

    def __post_init__(self):
        _identifier(self.task_id)
        _identifier(self.owner_id)
        if type(self.hop_limit) is not int or not 0 <= self.hop_limit <= MAX_HOPS:
            raise ContractError("invalid delegation limit")
        if type(self.visited) is not tuple or not 1 <= len(self.visited) <= self.hop_limit + 1:
            raise ContractError("invalid delegation history")
        for engine in self.visited:
            _identifier(engine)
        if self.visited[0] != self.owner_id or len(set(self.visited)) != len(self.visited):
            raise ContractError("invalid delegation history")

    @classmethod
    def start(cls, task_id, owner_id, hop_limit=MAX_HOPS):
        return cls(task_id, owner_id, (owner_id,), hop_limit)

    def forward(self, target_id):
        _identifier(target_id)
        if target_id in self.visited:
            raise PolicyViolation("delegation cycle")
        if len(self.visited) - 1 >= self.hop_limit:
            raise PolicyViolation("delegation limit exhausted")
        return DelegationRoute(self.task_id, self.owner_id,
                               self.visited + (target_id,), self.hop_limit)


def check_capability(manifest, operation):
    """A compatibility check only; an actual grant is independently required."""
    if type(manifest) is not EngineManifest:
        raise ContractError("invalid engine manifest")
    if type(operation) is not str or operation not in manifest.operations:
        raise PolicyViolation("operation not advertised")
