"""Persistent owner-consent store (P5 slice) — SQLite, single writer.

Consent records outlive a process so a revoked or expired grant stays denied
after a restart.  The store keeps only bounded identifiers and timestamps:
never a token value, a file path or any model output.

This is storage, not a security boundary. OS-level isolation, authenticated
workers and the broker that calls this store are separate P5 work items and
remain HOLD.
"""
from __future__ import annotations

import math
import os
import sqlite3
import stat
import threading
import time
from typing import Any, Dict, List, Optional

from .errors import ConfigurationError, StoreError

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    task_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    level TEXT NOT NULL,
    expires_at REAL NOT NULL,
    nonce TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    issued_at REAL NOT NULL,
    PRIMARY KEY (grant_id, recipient, task_id, field_name)
);
CREATE TABLE IF NOT EXISTS used_nonces (
    nonce TEXT PRIMARY KEY,
    used_at REAL NOT NULL
);
"""


class ConsentStore:
    """Owner consent records with replay protection and revocation."""

    def __init__(self, path: Optional[str] = None, *, thread_safe: bool = False) -> None:
        self._path = self._resolve(path)
        if self._path and not os.path.exists(self._path):
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        self._guard = threading.RLock() if thread_safe else None
        self._db = sqlite3.connect(self._path or ":memory:", isolation_level=None,
                                   check_same_thread=not thread_safe)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise StoreError("unsupported consent schema version")
        if version == 0:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = {}".format(SCHEMA_VERSION))
        else:
            present = {row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("grants", "used_nonces"):
                if table not in present:
                    raise StoreError("consent database is missing a required table")

    def _resolve(self, path: Optional[str]) -> Optional[str]:
        if path is None:
            return None
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ConfigurationError("consent path must be a bounded string")
        candidate = os.path.abspath(path)
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, "boru-consent.sqlite")
        if os.path.islink(candidate):
            raise ConfigurationError("consent path must not be a symlink")
        parent = os.path.dirname(candidate)
        if not os.path.isdir(parent):
            raise ConfigurationError("consent directory must already exist")
        mode = stat.S_IMODE(os.stat(parent).st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError("consent directory must not be group or world writable")
        if os.path.exists(candidate):
            file_mode = stat.S_IMODE(os.stat(candidate).st_mode)
            if file_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise ConfigurationError("consent file must not be group or world accessible")
            if os.stat(candidate).st_nlink != 1:
                raise ConfigurationError("consent file must not be hard-linked")
        return candidate

    # -- writes --------------------------------------------------------------
    def grant(self, *, grant_id: str, recipient: str, task_id: str, field_name: str, level: str,
              expires_at: float, nonce: str, now: Optional[float] = None) -> None:
        if self._guard is not None:
            with self._guard:
                return self._grant(grant_id, recipient, task_id, field_name, level, expires_at,
                                   nonce, now)
        return self._grant(grant_id, recipient, task_id, field_name, level, expires_at, nonce, now)

    def _grant(self, grant_id: str, recipient: str, task_id: str, field_name: str, level: str,
               expires_at: float, nonce: str, now: Optional[float] = None) -> None:
        if level not in ("L0", "L1", "L2"):
            raise ValueError("level must be L0, L1 or L2")
        for name, value, limit in (("grant_id", grant_id, 128), ("recipient", recipient, 128),
                                    ("task_id", task_id, 128), ("field_name", field_name, 64),
                                    ("nonce", nonce, 64)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(name + " must be a bounded non-empty string")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) or not math.isfinite(expires_at):
            raise ValueError("expires_at must be a finite timestamp")
        stamp = time.time() if now is None else now
        if expires_at <= stamp:
            raise ValueError("expires_at must be in the future")
        self._db.execute(
            "INSERT OR REPLACE INTO grants(grant_id, recipient, task_id, field_name, level, expires_at, nonce,"
            " revoked, issued_at) VALUES(?,?,?,?,?,?,?,0,?)",
            (grant_id, recipient, task_id, field_name, level, float(expires_at), nonce, stamp),
        )

    def revoke(self, grant_id: str) -> None:
        _bounded(grant_id, 128, "grant_id")
        if self._guard is not None:
            with self._guard:
                self._db.execute("UPDATE grants SET revoked = 1, expires_at = 0 WHERE grant_id = ?",
                                 (grant_id,))
            return
        self._db.execute("UPDATE grants SET revoked = 1, expires_at = 0 WHERE grant_id = ?",
                         (grant_id,))

    # -- reads ---------------------------------------------------------------
    def check(self, *, grant_id: str, recipient: str, task_id: str, field_name: str, nonce: str,
              now: Optional[float] = None) -> bool:
        if self._guard is not None:
            with self._guard:
                return self._check(grant_id, recipient, task_id, field_name, nonce, now)
        return self._check(grant_id, recipient, task_id, field_name, nonce, now)

    def _check(self, grant_id: str, recipient: str, task_id: str, field_name: str, nonce: str,
               now: Optional[float] = None) -> bool:
        stamp = time.time() if now is None else now
        row = self._db.execute(
            "SELECT level, expires_at, nonce, revoked FROM grants WHERE grant_id = ? AND recipient = ?"
            " AND task_id = ? AND field_name = ?",
            (grant_id, recipient, task_id, field_name),
        ).fetchone()
        if row is None or row["revoked"]:
            return False
        if row["nonce"] != nonce:
            return False
        if stamp >= row["expires_at"]:
            return False
        used = self._db.execute("SELECT 1 FROM used_nonces WHERE nonce = ?", (nonce,)).fetchone()
        if used is not None:
            return False
        self._db.execute("INSERT INTO used_nonces(nonce, used_at) VALUES(?,?)", (nonce, stamp))
        return True

    def active(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        if self._guard is not None:
            with self._guard:
                return self._active(now)
        return self._active(now)

    def _active(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        stamp = time.time() if now is None else now
        rows = self._db.execute(
            "SELECT grant_id, recipient, task_id, field_name, level, expires_at FROM grants"
            " WHERE revoked = 0 AND expires_at > ? ORDER BY expires_at", (stamp,)).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "ConsentStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _bounded(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(label + " must be a bounded non-empty string")
    return value
