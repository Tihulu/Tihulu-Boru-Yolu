"""Opaque token handle storage (P7 slice).

A token value is never stored in configuration, a prompt, a log, an issue body
or a CI artifact.  This store keeps an opaque handle and the encrypted-at-rest
value is left to the OS keyring / vault task (explicit HOLD); the on-disk file
contains only bounded metadata and is created owner-only.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..errors import ConfigurationError


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

    def register(self, handle: str, *, provider: str, account: str, scopes: tuple,
                 expires_at: Optional[float], security_level: str = "UNKNOWN") -> TokenHandle:
        if not isinstance(handle, str) or not handle.strip() or len(handle) > 128:
            raise ConfigurationError("handle must be a bounded non-empty string")
        if security_level not in ("UNKNOWN", "UNSUPPORTED", "REVOKED", "REFUSED"):
            security_level = "UNKNOWN"
        entry = TokenHandle(handle=handle, provider=provider, account=account,
                            scopes=tuple(scopes), expires_at=expires_at, security_level=security_level)
        self._handles[handle] = entry
        self._flush()
        return entry

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
