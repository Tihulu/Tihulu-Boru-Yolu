"""Local worker identity registry (P5 slice) — bounded, owner-confined.

A worker identity is created **by the owner**, in an owner-only directory, and
is valid for a bounded lifetime.  The secret is a random 256-bit value stored
owner-only (0600) and is never printed, logged, or returned by any API here.

This is an identity record, not a security boundary on its own.  Host
authentication of the *process* behind it, OS confinement and an independent
security review remain HOLD; the registry exists so those gates have something
concrete to harden.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigurationError


def _bounded(value: Any, limit: int = 128, label: str = "worker id") -> str:
    """Bounded, non-empty identifier used across the registry."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ConfigurationError(label + " must be a bounded non-empty string")
    return value

DEFAULT_TTL_SECONDS = 900.0
MAX_WORKERS = 8


@dataclass(frozen=True)
class WorkerRecord:
    """Bounded, non-secret worker metadata."""

    worker_id: str
    scopes: Tuple[str, ...]
    issued_at: float
    expires_at: float
    revoked: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        try:
            _bounded(self.worker_id, 128, "worker_id")
            for scope in self.scopes:
                _bounded(scope, 64, "worker scope")
        except ConfigurationError as exc:
            errors.append(str(exc))
        if len(set(self.scopes)) != len(self.scopes):
            errors.append("duplicate worker scopes")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, (int, float)) \
                or self.expires_at <= self.issued_at:
            errors.append("expires_at must follow issued_at")
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
                or not 1.0 <= float(ttl_seconds) <= 86400:
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
        return os.path.join(self._dir, "worker-{}.json".format(worker_id))

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
            record = WorkerRecord(worker_id=str(payload.get("worker_id", "")),
                                  scopes=tuple(str(s) for s in payload.get("scopes", ())),
                                  issued_at=float(payload.get("issued_at", 0.0)),
                                  expires_at=float(payload.get("expires_at", 0.0)),
                                  revoked=bool(payload.get("revoked", False)))
            secret = payload.get("secret")
            if record.validate() or not isinstance(secret, str) or len(secret) != 64:
                raise ConfigurationError("worker file is invalid")
            self._records[record.worker_id] = record
            self._secrets[record.worker_id] = secret

    # -- lifecycle -----------------------------------------------------------
    def create(self, worker_id: str, scopes: Tuple[str, ...], *, now: Optional[float] = None) -> WorkerRecord:
        _bounded(worker_id, 128, "worker_id")
        if not scopes:
            raise ConfigurationError("a worker must hold at least one scope")
        for scope in scopes:
            _bounded(scope, 64, "worker scope")
        if len(set(scopes)) != len(scopes):
            raise ConfigurationError("duplicate worker scopes")
        if worker_id in self._records:
            raise ConfigurationError("worker already exists")
        if len(self._records) >= MAX_WORKERS:
            raise ConfigurationError("worker registry is full")
        stamp = time.time() if now is None else float(now)
        record = WorkerRecord(worker_id=worker_id, scopes=tuple(scopes), issued_at=stamp,
                              expires_at=stamp + self.ttl_seconds)
        if record.validate():
            raise ConfigurationError("generated worker record is invalid")
        secret = secrets.token_hex(32)
        self._records[worker_id] = record
        self._secrets[worker_id] = secret
        if self._dir is not None:
            self._persist(record, secret)
        return record

    def _persist(self, record: WorkerRecord, secret: str) -> None:
        assert self._dir is not None
        target = self._file(record.worker_id)
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
        _bounded(worker_id, 128, "worker_id")
        record = self._records.get(worker_id)
        if record is None:
            raise ConfigurationError("unknown worker")
        # Revocation is the authority; the original expiry is preserved so the
        # record stays well-formed.
        revoked = WorkerRecord(worker_id=record.worker_id, scopes=record.scopes,
                               issued_at=record.issued_at, expires_at=record.expires_at,
                               revoked=True)
        self._records[worker_id] = revoked
        if self._dir is not None:
            self._persist(revoked, self._secrets[worker_id])
        return revoked

    def delete(self, worker_id: str) -> None:
        _bounded(worker_id, 128, "worker_id")
        if worker_id not in self._records:
            raise ConfigurationError("unknown worker")
        self._records.pop(worker_id)
        self._secrets.pop(worker_id)
        target = self._file(worker_id)
        if target and os.path.exists(target):
            os.unlink(target)

    # -- queries -------------------------------------------------------------
    def get(self, worker_id: str) -> Optional[WorkerRecord]:
        return self._records.get(_bounded(worker_id, 128, "worker_id"))

    def __enter__(self) -> "WorkerRegistry":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def all(self) -> List[WorkerRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def secret_for(self, worker_id: str) -> Optional[str]:
        """Returns the secret for owner-side session setup only."""
        return self._secrets.get(_bounded(worker_id, 128, "worker_id"))

    def valid(self, worker_id: str, secret: str, *, now: Optional[float] = None) -> bool:
        _bounded(worker_id, 128, "worker_id")
        record = self._records.get(worker_id)
        if record is None or record.revoked or record.validate():
            return False
        stored = self._secrets.get(worker_id)
        if not isinstance(stored, str) or not isinstance(secret, str):
            return False
        stamp = time.time() if now is None else float(now)
        if stamp >= record.expires_at:
            return False
        return secrets.compare_digest(stored.encode("utf-8"), secret.encode("utf-8"))
