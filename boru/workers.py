"""Local worker identity registry (P5).

An identity is created only by the owner, in an existing owner-only directory.
A worker id is a **single opaque segment**: it can never contain a path
separator, a parent reference, a control character or a drive letter, so a
crafted id cannot point a record file outside the registry.

An existing record is never overwritten by a create with the same id, and a
revoked or expired identity stays unusable until a new, distinct grant id is
issued. Timestamps must be finite.

This registry is an identity record, not a security boundary: host-level
process authentication and OS confinement are separate gates.
"""
from __future__ import annotations

import json
import math
import os
import time
import secrets
import stat
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigurationError

DEFAULT_TTL_SECONDS = 900.0
MAX_WORKERS = 8
SECRET_BYTES = 32
SECRET_HEX_CHARS = 2 * SECRET_BYTES

#: Characters that can never appear in a worker id.
_FORBIDDEN_ID_CHARS = ("/", "\\", ":", "..", "\x00", "\n", "\r", "\t", " ", "@", "?", "#", "%", "&", "=")


def _worker_id(value: Any) -> str:
    """Validate a worker id as one opaque, bounded segment."""
    if not isinstance(value, str):
        raise ConfigurationError("worker_id must be a string")
    if not value.strip() or len(value) > 64 or value.strip() != value:
        raise ConfigurationError("worker_id must be a bounded, trimmed token")
    for token in _FORBIDDEN_ID_CHARS:
        if token in value:
            raise ConfigurationError("worker_id contains an unsafe character")
    if value.startswith(".") or value.startswith("-"):
        raise ConfigurationError("worker_id must not start with a separator-like character")
    return value


def _scope(value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigurationError("scope must be a string")
    if not value.strip() or len(value) > 128 or value.strip() != value:
        raise ConfigurationError("scope must be a bounded, trimmed name")
    if any(c.isspace() for c in value) or any(token in value for token in ("/", "..", "\x00")):
        raise ConfigurationError("scope contains an unsafe character")
    return value


def _stamp(value: Any, label: str) -> float:
    """Require a finite, positive timestamp."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(label + " must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(label + " must be finite and positive")
    return float(value)


@dataclass(frozen=True)
class WorkerRecord:
    """Bounded, non-secret worker metadata (never contains a secret)."""

    worker_id: str
    scopes: Tuple[str, ...]
    issued_at: float
    expires_at: float
    revoked: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        try:
            _worker_id(self.worker_id)
        except ConfigurationError as exc:
            errors.append(str(exc))
        try:
            for scope in self.scopes:
                _scope(scope)
        except ConfigurationError as exc:
            errors.append(str(exc))
        if len(set(self.scopes)) != len(self.scopes):
            errors.append("duplicate worker scopes")
        if not self.scopes:
            errors.append("a worker must hold at least one scope")
        try:
            _stamp(self.issued_at, "issued_at")
            _stamp(self.expires_at, "expires_at")
        except ConfigurationError as exc:
            errors.append(str(exc))
        else:
            if self.expires_at <= self.issued_at:
                errors.append("expires_at must follow issued_at")
            if self.expires_at - self.issued_at > 86400:
                errors.append("worker lifetime is capped at 24 hours")
        if not isinstance(self.revoked, bool):
            errors.append("revoked must be a boolean")
        return errors

    def to_dict(self) -> dict:
        return {"worker_id": self.worker_id, "scopes": list(self.scopes),
                "issued_at": self.issued_at, "expires_at": self.expires_at,
                "revoked": self.revoked}


class WorkerRegistry:
    """Owner-created worker identities with bounded secrets and lifetimes."""

    def __init__(self, path: Optional[str] = None, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) \
                or not math.isfinite(ttl_seconds) or not 1.0 <= ttl_seconds <= 86400:
            raise ConfigurationError("ttl_seconds must be 1..86400")
        self.ttl_seconds = float(ttl_seconds)
        self._dir = self._resolve_dir(path)
        self._records: Dict[str, WorkerRecord] = {}
        self._secrets: Dict[str, str] = {}
        if self._dir is not None:
            self._load()

    def _resolve_dir(self, path: Optional[str]) -> Optional[str]:
        if path is None:
            return None
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ConfigurationError("worker directory must be a bounded string")
        candidate = os.path.abspath(path)
        if not os.path.isdir(candidate):
            raise ConfigurationError("worker directory must already exist")
        if os.path.islink(candidate):
            raise ConfigurationError("worker directory must not be a symlink")
        mode = stat.S_IMODE(os.stat(candidate).st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError("worker directory must not be group or world writable")
        return candidate

    def _file(self, worker_id: str) -> Optional[str]:
        if self._dir is None:
            return None
        safe = _worker_id(worker_id)
        target = os.path.join(self._dir, "worker-{}.json".format(safe))
        # The id is a single segment: the resolved name must stay inside.
        if os.path.dirname(os.path.abspath(target)) != self._dir:
            raise ConfigurationError("worker file must stay inside the registry")
        return target

    def _load(self) -> None:
        assert self._dir is not None
        for name in sorted(os.listdir(self._dir)):
            if not name.startswith("worker-") or not name.endswith(".json"):
                continue
            target = os.path.join(self._dir, name)
            if os.path.islink(target) or not os.path.isfile(target):
                raise ConfigurationError("worker file must be a regular, non-symlinked file")
            file_mode = stat.S_IMODE(os.stat(target).st_mode)
            if file_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise ConfigurationError("worker file must not be group or world accessible")
            with open(target, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ConfigurationError("worker file must contain an object")
            record = WorkerRecord(
                worker_id=payload.get("worker_id", ""),
                scopes=tuple(str(s) for s in payload.get("scopes", ())),
                issued_at=payload.get("issued_at"),
                expires_at=payload.get("expires_at"),
                revoked=bool(payload.get("revoked", False)),
            )
            secret = payload.get("secret")
            if record.validate():
                raise ConfigurationError("worker file is invalid")
            if not isinstance(secret, str) or len(secret) != SECRET_HEX_CHARS:
                raise ConfigurationError("worker file has an invalid secret")
            if any(c not in "0123456789abcdef" for c in secret):
                raise ConfigurationError("worker file has an invalid secret")
            if _worker_id(record.worker_id) != name[len("worker-"):-len(".json")]:
                raise ConfigurationError("worker file name does not match its id")
            self._records[record.worker_id] = record
            self._secrets[record.worker_id] = secret

    # -- lifecycle -----------------------------------------------------------
    def create(self, worker_id: str, scopes: Tuple[str, ...], *, now: Optional[float] = None) -> WorkerRecord:
        worker_id = _worker_id(worker_id)
        if not scopes:
            raise ConfigurationError("a worker must hold at least one scope")
        for scope in scopes:
            _scope(scope)
        if len(set(scopes)) != len(scopes):
            raise ConfigurationError("duplicate worker scopes")
        if worker_id in self._records:
            raise ConfigurationError("worker already exists")
        if len(self._records) >= MAX_WORKERS:
            raise ConfigurationError("worker registry is full")
        if now is None:
            stamp = time.time()
        elif isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now <= 0:
            raise ConfigurationError("now must be a finite positive timestamp")
        else:
            stamp = float(now)
        record = WorkerRecord(worker_id=worker_id, scopes=tuple(scopes), issued_at=stamp,
                              expires_at=stamp + self.ttl_seconds)
        if record.validate():
            raise ConfigurationError("generated worker record is invalid")
        secret = secrets.token_hex(SECRET_BYTES)
        self._records[worker_id] = record
        self._secrets[worker_id] = secret
        if self._dir is not None:
            self._persist(record, secret)
        return record

    def _persist(self, record: WorkerRecord, secret: str) -> None:
        assert self._dir is not None
        target = self._file(record.worker_id)
        assert target is not None
        if os.path.exists(target):
            raise ConfigurationError("worker record already exists")
        descriptor, temporary = tempfile.mkstemp(prefix="worker-", dir=self._dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"secret": secret, **record.to_dict()}, handle, ensure_ascii=True,
                          sort_keys=True)
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def revoke(self, worker_id: str) -> WorkerRecord:
        worker_id = _worker_id(worker_id)
        record = self._records.get(worker_id)
        if record is None:
            raise ConfigurationError("unknown worker")
        revoked = WorkerRecord(worker_id=record.worker_id, scopes=record.scopes,
                               issued_at=record.issued_at, expires_at=record.expires_at,
                               revoked=True)
        self._records[worker_id] = revoked
        if self._dir is not None:
            self._persist_overwrite(revoked, self._secrets[worker_id])
        return revoked

    def _persist_overwrite(self, record: WorkerRecord, secret: str) -> None:
        """Revocation replaces an existing record but never changes its id."""
        assert self._dir is not None
        target = self._file(record.worker_id)
        assert target is not None
        descriptor, temporary = tempfile.mkstemp(prefix="worker-", dir=self._dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"secret": secret, **record.to_dict()}, handle, ensure_ascii=True,
                          sort_keys=True)
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def delete(self, worker_id: str) -> None:
        worker_id = _worker_id(worker_id)
        if worker_id not in self._records:
            raise ConfigurationError("unknown worker")
        self._records.pop(worker_id)
        self._secrets.pop(worker_id)
        target = self._file(worker_id)
        if target and os.path.exists(target):
            os.unlink(target)

    # -- queries -------------------------------------------------------------
    def get(self, worker_id: str) -> Optional[WorkerRecord]:
        """Return a record, or ``None`` for an unknown but well-formed id.

        A malformed id is a caller error and refuses with ``ConfigurationError``
        rather than being silently treated as absent.
        """
        worker_id = _worker_id(worker_id)
        return self._records.get(worker_id)

    def __enter__(self) -> "WorkerRegistry":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release in-process state; persisted records are untouched."""
        self._records = {}
        self._secrets = {}

    def all(self) -> List[WorkerRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def secret_for(self, worker_id: str) -> Optional[str]:
        """Return the secret for owner-side session setup only.

        The secret is never logged, printed or placed in a prompt, log, ledger
        or connector request; holders are in-process registry instances.
        """
        try:
            worker_id = _worker_id(worker_id)
        except ConfigurationError:
            return None
        return self._secrets.get(worker_id)

    def valid(self, worker_id: str, secret: str, *, now: Optional[float] = None) -> bool:
        """Verify identity, secret (constant time), expiry and revocation."""
        try:
            worker_id = _worker_id(worker_id)
        except ConfigurationError:
            return False
        record = self._records.get(worker_id)
        if record is None or record.revoked or record.validate():
            return False
        if now is None:
            stamp = time.time()
        elif isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now <= 0:
            return False
        else:
            stamp = float(now)
        if stamp >= record.expires_at:
            return False
        stored = self._secrets.get(worker_id)
        if not isinstance(stored, str) or not isinstance(secret, str):
            return False
        return secrets.compare_digest(stored.encode("utf-8"), secret.encode("utf-8"))
