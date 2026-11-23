"""Persistent owner-consent store (P5).

Consent binds the grant id, recipient, task, operation, **resource alias**,
**field** and **level**, with an expiry and a single-use nonce. A revoked or
expired grant stays denied, and re-issuing the same grant id is refused, so a
revocation cannot be reset by replacement. Anti-replay state is bounded.

This store holds identifiers and timestamps only: never a token, a path or a
model output.
"""
from __future__ import annotations

import math
import os
import sqlite3
import stat
import threading
import time
from typing import Any, Dict, List, Optional

from .audit import safe_identifier
from .errors import ConfigurationError

#: 3 adds global grant-id uniqueness (F12) and the alias binding (F03).
SCHEMA_VERSION = 3
DEFAULT_TTL_SECONDS = 900.0
#: A declared resource alias may be a long owner-declared path.
MAX_ALIAS_LENGTH = 1024
MAX_NONCES = 8192
LEVELS = ("L0", "L1", "L2")
LEVEL_RANK = {"L0": 0, "L1": 1, "L2": 2}


class ConsentValidationError(ConfigurationError, ValueError):
    """A grant or check payload is malformed.

    It is both a configuration error and a ``ValueError`` so callers that
    validate owner input can branch on the familiar builtin class.
    """

    kind = "configuration_error"


class _null:
    """Null context manager so ``with`` reads cleanly without a guard."""

    def __enter__(self) -> "_null":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


def _stamp(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConsentValidationError(label + " must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ConsentValidationError(label + " must be finite and positive")
    return float(value)


def _identifier(value: Any, limit: int, label: str) -> str:
    """A bounded, path-free identifier (a path never belongs in a grant)."""
    try:
        return safe_identifier(value, limit, label)
    except Exception as exc:
        raise ConsentValidationError(str(exc))


def _binding(value: Any, limit: int, label: str) -> str:
    """A bounded binding token for one grant field.

    The resource alias is bound here, not judged: an owner-declared alias may
    be a short name or an absolute path, and whether a path is a *declared*
    resource is the broker's decision.  This store only guarantees the value
    is bounded, trimmed and free of control characters.
    """
    if not isinstance(value, str):
        raise ConsentValidationError(label + " must be a string")
    if not value.strip() or value.strip() != value or len(value) > limit:
        raise ConsentValidationError(label + " must be a bounded, trimmed string")
    for character in value:
        if ord(character) < 0x20 or ord(character) == 0x7F or character.isspace():
            raise ConsentValidationError(label + " contains an unsafe character")
    return value


class ConsentStore:
    """Owner consent records with replay protection, revocation and levels."""

    def __init__(self, path: Optional[str] = None, *, thread_safe: bool = False,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._path = self._resolve(path)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) \
                or not math.isfinite(ttl_seconds) or not 1.0 <= ttl_seconds <= 86400:
            raise ConfigurationError("ttl_seconds must be 1..86400")
        self.ttl_seconds = float(ttl_seconds)
        if self._path and not os.path.exists(self._path):
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        self._guard = threading.RLock() if thread_safe else None
        self._db = sqlite3.connect(self._path or ":memory:", isolation_level=None,
                                   check_same_thread=not thread_safe)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 2, SCHEMA_VERSION):
            raise ConfigurationError("unsupported consent schema version")
        if version == 0:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = {}".format(SCHEMA_VERSION))
        elif version == 2:
            self._migrate_v2_to_v3()
        else:
            self._verify_schema()

    # -- storage safety -------------------------------------------------------
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

    def _migrate_v2_to_v3(self) -> None:
        """Move a version-2 store to global grant-id uniqueness.

        A history that already re-uses a grant id cannot be migrated safely:
        the owner is told which id collides rather than one row being silently
        preferred over another.
        """
        duplicates = self._db.execute(
            "SELECT grant_id FROM grants GROUP BY grant_id HAVING COUNT(*) > 1").fetchall()
        if duplicates:
            raise ConfigurationError(
                "consent store re-uses a grant id across grants: "
                + ", ".join(sorted(row[0] for row in duplicates))
                + "; resolve it before upgrading")
        self._db.executescript(_MIGRATION_SQL)
        self._db.execute("PRAGMA user_version = {}".format(SCHEMA_VERSION))

    def _verify_schema(self) -> None:
        present = {row[0] for row in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("grants", "used_nonces"):
            if table not in present:
                raise ConfigurationError("consent database is missing its table")

    # -- writes ---------------------------------------------------------------
    def grant(self, *, grant_id: str, recipient: str, task_id: str, field_name: str,
              alias: str, level: str, expires_at: float, nonce: str,
              now: Optional[float] = None) -> None:
        """Issue one grant; an existing grant id is immutable.

        ``alias`` is the **owner-declared resource** the grant covers and is
        mandatory: a grant without one is refused, because an alias-less grant
        would authorize every resource - a wildcard the owner never granted.
        """
        for name, value, limit in (("grant_id", grant_id, 128), ("recipient", recipient, 64),
                                   ("task_id", task_id, 128), ("field_name", field_name, 64),
                                   ("nonce", nonce, 64)):
            _identifier(value, limit, name)
        if not isinstance(alias, str) or not alias.strip():
            raise ConsentValidationError("a grant must name its resource alias")
        _binding(alias, MAX_ALIAS_LENGTH, "alias")
        if level not in LEVELS:
            raise ConsentValidationError("level must be L0, L1 or L2")
        stamp = time.time() if now is None else _stamp(now, "now")
        expiry = _stamp(expires_at, "expires_at")
        if expiry <= stamp:
            raise ConsentValidationError("expires_at must follow now")
        with self._guard or _null():
            try:
                self._db.execute(
                    "INSERT INTO grants(grant_id, recipient, task_id, field_name, alias, level,"
                    " expires_at, nonce, revoked, issued_at) VALUES(?,?,?,?,?,?,?,?,0,?)",
                    (grant_id, recipient, task_id, field_name, alias or "", level,
                     expiry, nonce, stamp))
            except sqlite3.IntegrityError as exc:
                if "UNIQUE" in str(exc).upper():
                    raise ConsentValidationError("a grant with this id already exists") from exc
                raise ConsentValidationError("the grant could not be stored") from exc

    def revoke(self, grant_id: str) -> None:
        _identifier(grant_id, 128, "grant_id")
        with self._guard or _null():
            self._db.execute(
                "UPDATE grants SET revoked = 1, expires_at = 0 WHERE grant_id = ? AND revoked = 0",
                (grant_id,))

    # -- reads ----------------------------------------------------------------
    def check(self, *, grant_id: str, recipient: Optional[str] = None, task_id: str,
              field_name: str, nonce: str, alias: str, level: str = "L0",
              now: Optional[float] = None) -> bool:
        """Verify a request against the stored grant, including its level.

        ``recipient`` and ``alias`` are the caller's declaration: the broker
        passes the owner-configured consent subject and the requested resource,
        so a grant for one recipient, resource or disclosure level can never
        serve another.  Both are mandatory here: a check that names no resource
        is refused, because it cannot be bound to one.
        """
        if level not in LEVELS:
            return False
        for name, value, limit in (("grant_id", grant_id, 128), ("task_id", task_id, 128),
                                   ("field_name", field_name, 64), ("nonce", nonce, 64)):
            try:
                _identifier(value, limit, name)
            except Exception:
                return False
        if recipient is not None:
            try:
                _identifier(recipient, 64, "recipient")
            except Exception:
                return False
        try:
            _binding(alias, MAX_ALIAS_LENGTH, "alias")
        except Exception:
            return False
        stamp = _stamp(now, "now") if now is not None else time.time()
        with self._guard or _null():
            if recipient is None:
                rows = self._db.execute(
                    "SELECT recipient, level, expires_at, nonce, revoked, alias FROM grants"
                    " WHERE grant_id = ? AND task_id = ? AND field_name = ?",
                    (grant_id, task_id, field_name)).fetchall()
                if len(rows) != 1:
                    return False
                row = rows[0]
            else:
                row = self._db.execute(
                    "SELECT level, expires_at, nonce, revoked, alias FROM grants"
                    " WHERE grant_id = ? AND recipient = ? AND task_id = ? AND field_name = ?",
                    (grant_id, recipient, task_id, field_name)).fetchone()
            if row is None or row["revoked"]:
                return False
            if row["nonce"] != nonce:
                return False
            if stamp >= row["expires_at"]:
                return False
            # A grant whose stored alias is empty was written by an older build
            # (or by hand): it denies, it never behaves as a wildcard.
            if not row["alias"] or row["alias"] != alias:
                return False
            # The granted level must cover the requested level: no downgrade
            # into a wider disclosure.
            if LEVEL_RANK[level] > LEVEL_RANK[row["level"]]:
                return False
            used = self._db.execute(
                "SELECT 1 FROM used_nonces WHERE nonce = ?", (nonce,)).fetchone()
            if used is not None:
                return False
            # The nonce lives as long as the grant that carried it: pruning it
            # earlier would make a still-live grant replayable.
            self._db.execute("INSERT INTO used_nonces(nonce, used_at, expires_at) VALUES(?,?,?)",
                             (nonce, stamp, row["expires_at"]))
            return self._retain(nonce, now=stamp)

    def _retain(self, nonce: str, *, now: float) -> bool:
        """Drop nonces whose grant has expired; refuse when still at capacity.

        A nonce outlives the grant that carried it, so an expired grant's nonce
        can go.  A nonce whose grant is still live is never evicted: past the
        bound the store rolls this insert back and refuses, rather than making
        a live grant replayable.
        """
        self._db.execute("DELETE FROM used_nonces WHERE expires_at > 0 AND expires_at < ?", (now,))
        count = int(self._db.execute("SELECT COUNT(*) FROM used_nonces").fetchone()[0])
        if count > MAX_NONCES:
            self._db.execute("DELETE FROM used_nonces WHERE nonce = ?", (nonce,))
            return False
        return True

    def active(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        stamp = time.time() if now is None else _stamp(now, "now")
        rows = self._db.execute(
            "SELECT grant_id, recipient, task_id, field_name, alias, level, expires_at FROM grants"
            " WHERE revoked = 0 AND expires_at > ? ORDER BY expires_at", (stamp,)).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "ConsentStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT NOT NULL PRIMARY KEY,
    recipient TEXT NOT NULL,
    task_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    level TEXT NOT NULL,
    expires_at REAL NOT NULL,
    nonce TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    issued_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS used_nonces (
    nonce TEXT PRIMARY KEY,
    used_at REAL NOT NULL,
    expires_at REAL NOT NULL DEFAULT 0
);
"""

#: The version-2 schema allowed the same grant id under another
#: (recipient, task, field); version 3 makes the id globally unique.
_MIGRATION_SQL = """
CREATE TABLE grants_v3 (
    grant_id TEXT NOT NULL PRIMARY KEY,
    recipient TEXT NOT NULL,
    task_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    level TEXT NOT NULL,
    expires_at REAL NOT NULL,
    nonce TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    issued_at REAL NOT NULL
);
INSERT INTO grants_v3 (grant_id, recipient, task_id, field_name, alias, level,
                       expires_at, nonce, revoked, issued_at)
    SELECT grant_id, recipient, task_id, field_name,
           CASE WHEN alias IS NULL THEN '' ELSE alias END,
           level, expires_at, nonce, revoked, issued_at FROM grants;
DROP TABLE grants;
ALTER TABLE grants_v3 RENAME TO grants;
CREATE TABLE used_nonces_v3 (
    nonce TEXT PRIMARY KEY,
    used_at REAL NOT NULL,
    expires_at REAL NOT NULL DEFAULT 0
);
INSERT INTO used_nonces_v3 (nonce, used_at, expires_at)
    SELECT nonce, used_at, 0 FROM used_nonces;
DROP TABLE used_nonces;
ALTER TABLE used_nonces_v3 RENAME TO used_nonces;
"""
