"""Local, bounded task state store (stdlib SQLite).

The store is the durable memory of Boru Core.  It deliberately writes only to
an in-memory SQLite database by default, or to a **dedicated, owner-created
Boru state directory** when ``--state-dir`` is passed.  It never reads or
writes Jan, OpenCode or any other application's data, and it never grants
execution rights: a state file is bookkeeping, not an authorization boundary.
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
import sqlite3
import stat
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import ConfigurationError, DuplicateTask, StoreError

SCHEMA_VERSION = 1
STATE_FILENAME = "boru-state.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    fingerprint TEXT NOT NULL,
    envelope TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    at TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY (task_id, attempt_id)
);
"""


def _bounded(text: Any, limit: int, label: str) -> str:
    if not isinstance(text, str):
        raise ConfigurationError(label + " must be a string")
    if len(text) > limit:
        raise ConfigurationError(label + " exceeds the bounded limit")
    return text


def _canonical(envelope: Any) -> str:
    """Canonical, validated JSON used for idempotency fingerprinting."""
    try:
        data = envelope.to_dict() if hasattr(envelope, "to_dict") else dict(envelope)
    except Exception as exc:  # pragma: no cover - defensive
        raise DuplicateTask("envelope cannot be normalised") from exc
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class TaskStore:
    """Bounded, idempotent task state store."""

    def __init__(self, path: Optional[str] = None, *, max_records: int = 4096) -> None:
        if isinstance(max_records, bool) or not isinstance(max_records, int) or not 1 <= max_records <= 100000:
            raise ConfigurationError("max_records must be a positive bounded integer")
        self.max_records = max_records
        self._path, self._owns_dir = self._resolve(path)
        if self._path and not os.path.exists(self._path):
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        # A single-writer lock already exists on disk; this in-process lock only
        # serialises the SQLite handle across the (loopback) dashboard threads.
        self._guard = threading.RLock()
        self._db = sqlite3.connect(self._path or ":memory:", isolation_level=None,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock_fd = None
        self._closed = False
        if self._path:
            self._acquire_lock(self._path + ".lock")
        self._initialise()

    # -- lifecycle -----------------------------------------------------------
    def _resolve(self, path: Optional[str]) -> Tuple[Optional[str], bool]:
        """Resolve ``--state-dir`` to a dedicated state database path.

        ``--state-dir`` names an existing, owner-only directory; the state file
        and its lock are created inside it.  Nothing outside that directory is
        read or written.
        """
        if path is None:
            return None, False
        root = os.path.abspath(path)
        if not os.path.isdir(root):
            raise ConfigurationError("--state-dir must be an existing directory")
        root_mode = stat.S_IMODE(os.stat(root).st_mode)
        if root_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError("state directory must not be group or world writable")
        if os.path.islink(root):
            raise ConfigurationError("state directory must not be a symlink")
        candidate = os.path.join(root, STATE_FILENAME)
        if os.path.islink(candidate):
            raise ConfigurationError("state file must not be a symlink")
        if os.path.exists(candidate):
            if not os.path.isfile(candidate):
                raise ConfigurationError("state file must be a regular file")
            mode = stat.S_IMODE(os.stat(candidate).st_mode)
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise ConfigurationError("state file must not be group or world accessible")
            if os.stat(candidate).st_nlink != 1:
                raise ConfigurationError("state file must not be hard-linked")
            if os.stat(root).st_uid != os.stat(candidate).st_uid:
                raise ConfigurationError("state file must belong to the same owner")
        return candidate, False

    def _acquire_lock(self, lock_path: str) -> None:
        if os.path.isdir(lock_path) or os.path.islink(lock_path):
            raise ConfigurationError("lock path must be a regular file")
        try:
            os.close(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600))
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise ConfigurationError("state directory is not writable")
            raise ConfigurationError("lock file cannot be created")
        try:
            os.chmod(lock_path, 0o600)
            fd = os.open(lock_path, os.O_RDWR)
        except OSError as exc:
            raise ConfigurationError("lock file cannot be opened")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise ConfigurationError("another Boru process owns this state directory")
        self._lock_fd = fd

    def _initialise(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise StoreError("unsupported state schema version: {}".format(version))
        if version == 0:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = {}".format(SCHEMA_VERSION))
        else:
            self._verify_schema()

    def _verify_schema(self) -> None:
        expected = {"tasks", "events", "attempts"}
        rows = self._db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        present = {row[0] for row in rows}
        for table in expected:
            if table not in present:
                raise StoreError("state database is missing required table")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._db.close()
        finally:
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None

    def __enter__(self) -> "TaskStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- writes --------------------------------------------------------------
    def submit(self, task_id: str, idempotency_key: str, envelope: Any, state: str, at: str) -> Tuple[bool, Dict[str, Any]]:
        """Insert a task idempotently; returns ``(created, stored)``."""
        with self._guard:
            return self._submit(task_id, idempotency_key, envelope, state, at)

    def _submit(self, task_id: str, idempotency_key: str, envelope: Any, state: str, at: str) -> Tuple[bool, Dict[str, Any]]:
        task_id = _bounded(task_id, 128, "task_id")
        idempotency_key = _bounded(idempotency_key, 128, "idempotency_key")
        fingerprint = _canonical(envelope)
        _bounded(state, 32, "state")
        _bounded(at, 40, "timestamp")
        try:
            self._db.execute(
                "INSERT INTO tasks(task_id, idempotency_key, fingerprint, envelope, state, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (task_id, idempotency_key, fingerprint, fingerprint, state, at, at),
            )
            return True, self.get(task_id)
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "idempotency_key" not in message and "task_id" not in message:
                raise StoreError("task could not be recorded")
        row = self._db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            row = self._db.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if row is None:
            raise StoreError("task could not be recorded")
        if row["fingerprint"] != fingerprint:
            raise DuplicateTask("idempotency key was already recorded with different contents")
        return False, dict(row)

    def count(self) -> int:
        with self._guard:
            return int(self._db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])

    def ensure_capacity(self) -> None:
        with self._guard:
            if int(self._db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]) >= self.max_records:
                raise StoreError("task record limit reached")

    def transition(self, task_id: str, expected: str, target: str, reason: str, at: str) -> str:
        """Compare-and-set state transition; returns the previous state."""
        with self._guard:
            return self._transition(task_id, expected, target, reason, at)

    def _transition(self, task_id: str, expected: str, target: str, reason: str, at: str) -> str:
        task_id = _bounded(task_id, 128, "task_id")
        reason = _bounded(reason, 200, "reason")
        cursor = self._db.execute(
            "UPDATE tasks SET state = ?, updated_at = ? WHERE task_id = ? AND state = ?",
            (target, at, task_id, expected),
        )
        if cursor.rowcount != 1:
            row = self._db.execute("SELECT state FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                raise StoreError("unknown task")
            raise StoreError("task state changed concurrently")
        self._db.execute(
            "INSERT INTO events(task_id, at, from_state, to_state, reason) VALUES(?,?,?,?,?)",
            (task_id, at, expected, target, reason),
        )
        return expected

    def save_result(self, task_id: str, attempt_id: str, result: Any) -> None:
        with self._guard:
            return self._save_result(task_id, attempt_id, result)

    def _save_result(self, task_id: str, attempt_id: str, result: Any) -> None:
        _bounded(attempt_id, 128, "attempt_id")
        payload = json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, sort_keys=True, ensure_ascii=True)
        if len(payload) > 256 * 1024:
            raise StoreError("result exceeds the bounded size")
        self._db.execute(
            "INSERT OR REPLACE INTO attempts(task_id, attempt_id, result) VALUES(?,?,?)",
            (task_id, attempt_id, payload),
        )

    # -- reads ---------------------------------------------------------------
    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._guard:
            return self._get(task_id)

    def _get(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute("SELECT * FROM tasks WHERE task_id = ?", (_bounded(task_id, 128, "task_id"),)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["events"] = [dict(r) for r in self._db.execute(
            "SELECT task_id, at, from_state, to_state, reason FROM events WHERE task_id = ? ORDER BY seq", (task_id,)
        )]
        data["attempts"] = [json.loads(r["result"]) for r in self._db.execute(
            "SELECT task_id, attempt_id, result FROM attempts WHERE task_id = ? ORDER BY attempt_id", (task_id,)
        )]
        return data

    def queued(self, limit: int = 32) -> List[Dict[str, Any]]:
        with self._guard:
            return self._queued(limit)

    def _queued(self, limit: int) -> List[Dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
            raise StoreError("limit must be a bounded positive integer")
        rows = self._db.execute(
            "SELECT task_id, state, created_at FROM tasks WHERE state = ? ORDER BY created_at, rowid LIMIT ?",
            ("QUEUED", limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def envelope(self, task_id: str) -> Dict[str, Any]:
        """Return the stored canonical envelope for a task."""
        with self._guard:
            row = self._db.execute("SELECT envelope FROM tasks WHERE task_id = ?", (_bounded(task_id, 128, "task_id"),)).fetchone()
        if row is None:
            raise StoreError("unknown task")
        try:
            return json.loads(row["envelope"])
        except json.JSONDecodeError:
            raise StoreError("stored envelope is corrupt")

    def pending(self) -> List[Dict[str, Any]]:
        with self._guard:
            rows = self._db.execute(
                "SELECT task_id, state FROM tasks WHERE state IN ('RUNNING','VERIFYING') ORDER BY created_at"
            ).fetchall()
            return [dict(row) for row in rows]

    def by_state(self, states: Iterable[str]) -> List[Dict[str, Any]]:
        with self._guard:
            return self._by_state(states)

    def _by_state(self, states: Iterable[str]) -> List[Dict[str, Any]]:
        wanted = tuple(states)
        if not wanted:
            return []
        placeholders = ",".join("?" for _ in wanted)
        rows = self._db.execute(
            "SELECT task_id, state FROM tasks WHERE state IN ({}) ORDER BY created_at".format(placeholders),
            wanted,
        ).fetchall()
        return [dict(row) for row in rows]
