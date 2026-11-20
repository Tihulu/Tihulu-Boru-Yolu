"""PKCE / state / nonce helpers (P7 slice, RFC 7636-style).

Deterministic, dependency-free primitives used by the OAuth flow. Nothing here
touches the network; tokens are produced only by the provider.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Tuple

from ..errors import ConfigurationError

MIN_VERIFIER = 43
MAX_VERIFIER = 128


def _b64url_no_padding(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class PkcePair:
    """A code verifier and its S256 challenge."""

    verifier: str
    challenge: str
    method: str = "S256"

    @classmethod
    def generate(cls) -> "PkcePair":
        verifier = _b64url_no_padding(secrets.token_bytes(64))
        if not MIN_VERIFIER <= len(verifier) <= MAX_VERIFIER:  # pragma: no cover - token size
            raise ConfigurationError("generated verifier is out of bounds")
        challenge = _b64url_no_padding(hashlib.sha256(verifier.encode("ascii")).digest())
        return cls(verifier=verifier, challenge=challenge)

    @classmethod
    def from_verifier(cls, verifier: str) -> "PkcePair":
        if not isinstance(verifier, str) or not MIN_VERIFIER <= len(verifier) <= MAX_VERIFIER:
            raise ConfigurationError("verifier length is out of bounds")
        challenge = _b64url_no_padding(hashlib.sha256(verifier.encode("ascii")).digest())
        return cls(verifier=verifier, challenge=challenge)


def random_state() -> str:
    """Opaque CSRF state value."""
    return _b64url_no_padding(secrets.token_bytes(32))


def random_nonce() -> str:
    """Opaque replay-protection nonce for the ID token."""
    return _b64url_no_padding(secrets.token_bytes(32))


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two opaque values without leaking length or content timing."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def bounded_text(value: str, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ConfigurationError(label + " must be a bounded non-empty string")
    return value


def scopes(values: Tuple[str, ...]) -> Tuple[str, ...]:
    for value in values:
        bounded_text(value, 64, "scope")
    if len(set(values)) != len(values):
        raise ConfigurationError("duplicate scopes")
    return tuple(sorted(values))
