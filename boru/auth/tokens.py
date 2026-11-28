"""Opaque token handle storage (P7 slice).

A token value is never stored in configuration, a prompt, a log, an issue body
or a CI artifact.  This store keeps an opaque handle and the encrypted-at-rest
value is left to the OS keyring / vault task (explicit HOLD); the on-disk file
contains only bounded metadata and is created owner-only.
"""
from __future__ import annotations

import json
import math
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..errors import ConfigurationError

#: Bounded handle metadata: an unbounded provider, account or scope list could
#: turn the owner-only metadata file into a slow-growing, unparseable record.
MAX_PROVIDER = 64
MAX_ACCOUNT = 256
MAX_SCOPES = 16
#: A persisted expiry must be a finite positive timestamp, and never further
#: than a decade ahead: a NaN or infinite value would make a token that no
#: comparison can ever call expired.
MAX_EXPIRY_YEARS = 10


@dataclass(frozen=True)
class TokenHandle:
    """What the rest of Boru Core is allowed to see about a token."""

    handle: str
    provider: str
    account: str
    scopes: tuple
    expires_at: Optional[float]
    security_level: str = "UNKNOWN"

    def to_dict(self) -> dict:
        return {
            "handle": self.handle,
            "provider": self.provider,
            "account": self.account,
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
            "security_level": self.security_level,
        }


class TokenVault:
    """In-memory handle registry with optional metadata persistence."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._handles: Dict[str, TokenHandle] = {}
        self._path = self._resolve(path)
        if self._path is not None and os.path.exists(self._path):
            self._load()

    def _resolve(self, path: Optional[str]) -> Optional[str]:
        if path is None:
            return None
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ConfigurationError("vault path must be a bounded string")
        candidate = os.path.abspath(path)
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, "boru-token-handles.json")
        if os.path.islink(candidate):
            raise ConfigurationError("vault path must not be a symlink")
        parent = os.path.dirname(candidate)
        if not os.path.isdir(parent):
            raise ConfigurationError("vault directory must already exist")
        mode = stat.S_IMODE(os.stat(parent).st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError("vault directory must not be group or world writable")
        if os.path.exists(candidate):
            file_mode = stat.S_IMODE(os.stat(candidate).st_mode)
            if file_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise ConfigurationError("vault file must not be group or world accessible")
        return candidate

    def _load(self) -> None:
        """Load existing handles from the owner-only metadata file."""
        assert self._path is not None
        if os.path.islink(self._path) or not os.path.isfile(self._path):
            raise ConfigurationError("vault path must be a regular, non-symlinked file")
        file_mode = stat.S_IMODE(os.stat(self._path).st_mode)
        if file_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ConfigurationError("vault file must not be group or world accessible")
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            raise ConfigurationError("vault file cannot be parsed")
        if not isinstance(payload, list) or len(payload) > 256:
            raise ConfigurationError("vault file must contain bounded handle metadata")
        for entry in payload:
            if not isinstance(entry, dict):
                raise ConfigurationError("vault entries must be objects")
            record = TokenHandle(
                handle=str(entry.get("handle", "")),
                provider=str(entry.get("provider", "")),
                account=str(entry.get("account", "")),
                scopes=tuple(str(s) for s in entry.get("scopes", ())),
                expires_at=entry.get("expires_at"),
                security_level=str(entry.get("security_level", "UNKNOWN")),
            )
            if not record.handle.strip() or len(record.handle) > 128:
                raise ConfigurationError("vault entry handle is invalid")
            if record.security_level not in ("UNKNOWN", "UNSUPPORTED", "REVOKED", "REFUSED"):
                raise ConfigurationError("vault entry security level is invalid")
            record = TokenHandle(
                handle=record.handle, provider=self._bounded(record.provider, MAX_PROVIDER, "provider"),
                account=self._bounded(record.account, MAX_ACCOUNT, "account"),
                scopes=tuple(self._bounded(value, 64, "scope") for value in record.scopes),
                expires_at=self._expiry(record.expires_at, None),
                security_level=record.security_level)
            self._handles[record.handle] = record

    def register(self, handle: str, *, provider: str, account: str, scopes: tuple,
                 expires_at: Optional[float], security_level: str = "UNKNOWN",
                 now: Optional[float] = None) -> TokenHandle:
        if not isinstance(handle, str) or not handle.strip() or len(handle) > 128:
            raise ConfigurationError("handle must be a bounded non-empty string")
        provider = self._bounded(provider, MAX_PROVIDER, "provider")
        account = self._bounded(account, MAX_ACCOUNT, "account")
        cleaned = tuple(self._bounded(value, 64, "scope") for value in scopes)
        if len(cleaned) > MAX_SCOPES or len(set(cleaned)) != len(cleaned):
            raise ConfigurationError("scopes must be a bounded set")
        expires_at = self._expiry(expires_at, now)
        if security_level not in ("UNKNOWN", "UNSUPPORTED", "REVOKED", "REFUSED"):
            security_level = "UNKNOWN"
        entry = TokenHandle(handle=handle, provider=provider, account=account,
                            scopes=cleaned, expires_at=expires_at, security_level=security_level)
        self._handles[handle] = entry
        self._flush()
        return entry

    @staticmethod
    def _bounded(value: Any, limit: int, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or value.strip() != value or len(value) > limit:
            raise ConfigurationError(label + " must be a bounded, trimmed string")
        return value

    @staticmethod
    def _expiry(value: Any, now: Optional[float]) -> Optional[float]:
        """A finite, positive, sane timestamp or nothing at all."""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ConfigurationError("expires_at must be a finite timestamp")
        stamp = time.time() if now is None else float(now)
        horizon = stamp + MAX_EXPIRY_YEARS * 366 * 86400
        if not 0 < float(value) <= horizon:
            raise ConfigurationError("expires_at is outside the sane range")
        return float(value)

    def get(self, handle: str) -> Optional[TokenHandle]:
        return self._handles.get(handle)

    def revoke(self, handle: str) -> TokenHandle:
        entry = self._handles.get(handle)
        if entry is None:
            raise ConfigurationError("unknown handle")
        revoked = TokenHandle(handle=entry.handle, provider=entry.provider, account=entry.account,
                              scopes=entry.scopes, expires_at=entry.expires_at, security_level="REVOKED")
        self._handles[handle] = revoked
        self._flush()
        return revoked

    def list(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self._handles.values()]

    def _flush(self) -> None:
        if self._path is None:
            return
        payload = [entry.to_dict() for entry in self._handles.values()]
        descriptor, temporary = tempfile.mkstemp(prefix="boru-vault-", dir=os.path.dirname(self._path))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temporary, self._path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
