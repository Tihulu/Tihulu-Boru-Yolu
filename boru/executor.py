"""Bounded local worker (P5 slice): typed, alias-confined, read-only.

The worker performs the *local acquisition and reduction* steps of the Privacy
Bridge: it opens only a declared alias, resolves a target **component-wise
without following any symlink**, and returns typed fields — never raw content.

* `probe_path_alias` -> ``{"exists": bool, "type": "file"|"dir"|"other", "size": int|None}``
* `read_file_alias` -> ``{"exists": bool, "size": int, "line_count": int}``
* `list_dir_alias` -> ``{"exists": bool, "entry_count": int}``

Every acquisition is bound to a **receipt the worker verifies**: it must carry
an authentic authentication tag under this worker's authorization key, must be
unexpired, and must name exactly the requested fields. A receipt that fails
verification is refused before any filesystem access.

File *content*, names, owners, timestamps, environment and any raw output stay
local: emitting them is a separate L2 disclosure decision that this slice does
not implement.  No subprocess, shell, network or mutation is performed, and a
directory is never traversed outside its alias.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .authorization import AuthorizationReceipt
from .broker import ScopeAllowlist
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
    """Read-only, alias-confined executor that verifies every receipt."""

    def __init__(self, aliases: ScopeAllowlist, *, authorization_key: bytes) -> None:
        if aliases.validate():
            raise PolicyViolation("resource allowlist is invalid")
        if not isinstance(authorization_key, (bytes, bytearray)) or len(authorization_key) != 32:
            raise PolicyViolation("authorization key must be 256 bits")
        self.aliases = aliases
        self.authorization_key = bytes(authorization_key)

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
        receipt.verify(self.authorization_key, now=now, requested_fields=fields)
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
            return self._run(receipt.operation, alias, root, receipt.target, fields)
        finally:
            os.close(root)

    def _run(self, operation: str, alias: str, root: int, target: str,
             fields: Tuple[str, ...]) -> Acquisition:
        if operation == "probe_path_alias":
            return Acquisition(operation, alias, self._probe(root, target, fields))
        if operation == "list_dir_alias":
            return Acquisition(operation, alias, self._count_entries(root))
        if operation == "read_file_alias":
            return Acquisition(operation, alias, self._read_target(root, target, fields))
        if operation == "run_synthetic_command":
            return Acquisition(operation, alias, {"ok": True})
        raise PolicyViolation("operation is not executable by this worker")

    # -- bounded, typed helpers ---------------------------------------------
    def _probe(self, root: int, target: str, fields: Tuple[str, ...]) -> Dict[str, Any]:
        """Probe a single entry inside the alias, or the alias root itself."""
        descriptor = self._open_target(root, target)
        if descriptor is None:
            return {"exists": False, "type": None, "size": None}
        try:
            info = os.fstat(descriptor)
        finally:
            if descriptor != root:
                os.close(descriptor)
        return {"exists": True, "type": _kind(info.st_mode),
                "size": info.st_size if stat.S_ISREG(info.st_mode) else None}

    def _read_target(self, root: int, target: str, fields: Tuple[str, ...]) -> Dict[str, Any]:
        """Real, bounded read metadata for one regular file inside the alias."""
        if not target:
            raise PolicyViolation("read_file_alias requires a single target name")
        descriptor = self._open_target(root, target)
        if descriptor is None:
            return {"exists": False, "size": None, "line_count": None}
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise PolicyViolation("read_file_alias applies to a regular file only")
            if info.st_size > MAX_FILE_SCAN_BYTES:
                raise PolicyViolation("file exceeds the bounded scan size")
            return {"exists": True, "size": info.st_size,
                    "line_count": _count_lines(descriptor, info.st_size)}
        finally:
            if descriptor != root:
                os.close(descriptor)

    def _count_entries(self, root: int) -> Dict[str, Any]:
        """Count entries without classifying them: names never leave this call."""
        seen = 0
        with os.scandir(root) as entries:
            for _entry in entries:
                seen += 1
                if seen >= MAX_ENTRY_SCAN:
                    break
        return {"exists": True, "entry_count": seen}

    def _open_target(self, root: int, target: str) -> Optional[int]:
        """Resolve one component inside the alias, never following a symlink.

        The alias root was already opened with ``O_NOFOLLOW``.  A target is a
        single segment resolved **relative to that descriptor** with
        ``dir_fd``: no intermediate path is constructed, so no ``..`` chain,
        double-separator or symlinked directory can escape the alias.
        """
        if not target:
            return root
        if any(token in target for token in ("/", "\\", "\x00")) or target in (".", ".."):
            raise PolicyViolation("target must be a single name inside the alias")
        try:
            return os.open(target, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
        except FileNotFoundError:
            return None
        except NotADirectoryError:
            raise PolicyViolation("target parent is not a directory")
        except OSError as exc:
            raise PolicyViolation("target could not be resolved: " + str(exc.errno or "refused"))


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    return "other"


def _count_lines(descriptor: int, size: int) -> int:
    """Count newlines with bounded reads; content is never retained."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    remaining = size
    count = 0
    while remaining > 0:
        chunk = os.read(descriptor, min(65536, remaining))
        if not chunk:
            break
        count += chunk.count(NEWLINE)
        remaining -= len(chunk)
    return count
