"""Local, bounded, append-only rejection ledger (P5/P8 audit slice).

Every denial — policy, broker, disclosure, connector, provider, budget,
scheduler, executor, review — is recorded once, locally, with sanitized fields.
The ledger deliberately holds **no payloads, no paths, no tokens and no
provider text**: only a category, a bounded subject identifier, a stable reason
code and a bounded detail kind. There is no update or delete API, so an audit
entry cannot be rewritten; retention is bounded by a documented cap, and
pruning the oldest rows is the only mutation.

This sink is the audit trail referenced by `docs/OPERATIONS.md` ("compact
sanitized audit events locally") and by the connector issues; it is not a
security boundary and cannot prove a live operation happened.
"""
from __future__ import annotations

import math
import os
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigurationError

SCHEMA_VERSION = 1
DEFAULT_CAP = 4096
MAX_SUBJECT = 128
MAX_REASON = 64
MAX_DETAIL = 64

CATEGORIES: Tuple[str, ...] = (
    "policy", "contract", "broker", "disclosure", "connector", "provider",
    "budget", "scheduler", "executor", "review", "store", "config",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rejections (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail_kind TEXT NOT NULL
);
"""


def _bounded(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ConfigurationError(label + " must be a bounded non-empty string")
    return value


class RejectionLedger:
    """Append-only, bounded, owner-directory-confined audit sink."""

    def __init__(self, path: Optional[str] = None, *, cap: int = DEFAULT_CAP) -> None:
        if isinstance(cap, bool) or not isinstance(cap, int) or not 16 <= cap <= 100000:
            raise ConfigurationError("cap must be 16..100000")
        self.cap = cap
        self._resolved = self._resolve(path)
        if self._resolved and not os.path.exists(self._resolved):
            descriptor = os.open(self._resolved, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        self._guard = threading.RLock()
        self._db = sqlite3.connect(self._resolved or ":memory:", isolation_level=None,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise ConfigurationError("unsupported audit schema version")
        if version == 0:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = {}".format(SCHEMA_VERSION))
        else:
            present = {row[0] for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "rejections" not in present:
                raise ConfigurationError("audit database is missing its table")

    def _resolve(self, path: Optional[str]) -> Optional[str]:
        if path is None:
            return None
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ConfigurationError("ledger path must be a bounded string")
        candidate = os.path.abspath(path)
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, "boru-audit.sqlite")
        if os.path.islink(candidate):
            raise ConfigurationError("ledger path must not be a symlink")
        parent = os.path.dirname(candidate)
        if not os.path.isdir(parent):
            raise ConfigurationError("ledger directory must already exist")
        mode = stat.S_IMODE(os.stat(parent).st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError("ledger directory must not be group or world writable")
        if os.path.exists(candidate):
            file_mode = stat.S_IMODE(os.stat(candidate).st_mode)
            if file_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise ConfigurationError("ledger file must not be group or world accessible")
        return candidate

    # -- write ---------------------------------------------------------------
    def record(self, category: str, subject: str, reason: str, detail_kind: str = "none",
               at: Optional[float] = None) -> None:
        """Append one sanitized rejection entry (append-only)."""
        if category not in CATEGORIES:
            raise ConfigurationError("unknown audit category")
        _bounded(subject, MAX_SUBJECT, "subject")
        _bounded(reason, MAX_REASON, "reason")
        _bounded(detail_kind, MAX_DETAIL, "detail_kind")
        if at is None:
            stamp = time.time()
        elif isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at) or at <= 0:
            raise ConfigurationError("at must be a finite positive timestamp")
        else:
            stamp = float(at)
        with self._guard:
            self._db.execute(
                "INSERT INTO rejections(at, category, subject, reason, detail_kind) VALUES(?,?,?,?,?)",
                (stamp, category, subject, reason, detail_kind),
            )
            self._prune()

    def _prune(self) -> None:
        count = int(self._db.execute("SELECT COUNT(*) FROM rejections").fetchone()[0])
        if count > self.cap:
            excess = count - self.cap
            self._db.execute(
                "DELETE FROM rejections WHERE seq IN (SELECT seq FROM rejections ORDER BY seq LIMIT ?)",
                (excess,),
            )

    # -- read ----------------------------------------------------------------
    def recent(self, limit: int = 64) -> List[Dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1024:
            raise ConfigurationError("limit must be 1..1024")
        with self._guard:
            rows = self._db.execute(
                "SELECT at, category, subject, reason, detail_kind FROM rejections"
                " ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._guard:
            return int(self._db.execute("SELECT COUNT(*) FROM rejections").fetchone()[0])

    def counts_by_category(self) -> Dict[str, int]:
        with self._guard:
            rows = self._db.execute(
                "SELECT category, COUNT(*) AS total FROM rejections GROUP BY category").fetchall()
        return {row["category"]: int(row["total"]) for row in rows}

    def close(self) -> None:
        with self._guard:
            self._db.close()

    def __enter__(self) -> "RejectionLedger":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
