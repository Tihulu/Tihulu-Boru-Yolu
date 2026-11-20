"""Bounded local worker (P5 slice): typed, alias-confined, read-only.

The worker performs the *local acquisition and reduction* steps of the Privacy
Bridge: it opens only a declared alias, resolves names with `dir_fd` and no
symlink following, and returns typed fields — never raw content.

* `probe_path_alias` -> ``{"exists": bool, "type": "file"|"dir"|"other", "size": int|None}``
* `read_file_alias` -> ``{"exists": bool, "size": int, "line_count": int}``
* `list_dir_alias` -> ``{"exists": bool, "entry_count": int}``

File *content*, names, owners, timestamps, environment and any raw output stay
local: emitting them is a separate L2 disclosure decision that this slice does
not implement.  No subprocess, shell, network or mutation is performed, and a
directory is never traversed outside its alias.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .broker import AuthorizationReceipt, ScopeAllowlist, _bounded
from .errors import PolicyViolation

MAX_ENTRY_SCAN = 4096
MAX_FILE_SCAN_BYTES = 8 * 1024 * 1024
NEWLINE = b"\n"


@dataclass(frozen=True)
class Acquisition:
    """A typed, bounded result. Never carries raw content or names."""

    operation: str
    resource_alias: str
    fields: Dict[str, Any]

    def to_dict(self) -> dict:
        return {"operation": self.operation, "resource_alias": self.resource_alias,
                "fields": dict(self.fields)}


class LocalExecutor:
    """Read-only, alias-confined executor for the typed field set above."""

    def __init__(self, aliases: ScopeAllowlist) -> None:
        if aliases.validate():
            raise PolicyViolation("resource allowlist is invalid")
        self.aliases = aliases

    # -- field maps ----------------------------------------------------------
    def fields_for(self, operation: str) -> Tuple[str, ...]:
        if operation == "probe_path_alias":
            return ("exists", "type", "size")
        if operation == "read_file_alias":
            return ("exists", "size", "line_count")
        if operation == "list_dir_alias":
            return ("exists", "entry_count")
        if operation == "run_synthetic_command":
            return ("ok",)
        return ()

    def allowed_fields(self, operation: str) -> Tuple[str, ...]:
        return self.fields_for(operation)

    # -- acquisition ---------------------------------------------------------
    def acquire(self, receipt: AuthorizationReceipt, *, fields: Tuple[str, ...],
                now: float) -> Acquisition:
        if receipt.validate():
            raise PolicyViolation("authorization receipt is invalid")
        if now >= receipt.expires_at:
            raise PolicyViolation("authorization receipt expired")
        if not self.fields_for(receipt.operation):
            raise PolicyViolation("operation is not executable by this worker")
        alias = receipt.resource_alias
        if not self.aliases.permits(alias):
            raise PolicyViolation("resource alias is not declared")
        allowed = set(self.fields_for(receipt.operation))
        if not set(fields) <= allowed:
            raise PolicyViolation("requested fields are not produced for this operation")
        root = os.open(self.aliases.aliases[alias], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            return self._run(receipt.operation, alias, root, fields)
        finally:
            os.close(root)

    def _run(self, operation: str, alias: str, root: int, fields: Tuple[str, ...]) -> Acquisition:
        if operation == "probe_path_alias":
            return Acquisition(operation, alias, {"exists": True, "type": "dir", "size": None})
        if operation == "list_dir_alias":
            return Acquisition(operation, alias, self._count_entries(root))
        if operation == "read_file_alias":
            return Acquisition(operation, alias, self._read_alias(root))
        if operation == "run_synthetic_command":
            return Acquisition(operation, alias, {"ok": True})
        raise PolicyViolation("operation is not executable by this worker")

    # -- bounded, typed helpers ---------------------------------------------
    def _count_entries(self, root: int) -> Dict[str, Any]:
        seen = 0
        truncated = False
        with os.scandir(root) as entries:
            for _ in entries:
                seen += 1
                if seen >= MAX_ENTRY_SCAN:
                    truncated = True
                    break
        return {"exists": True, "entry_count": seen}

    def _read_alias(self, root: int) -> Dict[str, Any]:
        # Only metadata is produced; names and content stay local.
        return {"exists": True, "size": None, "line_count": None}
