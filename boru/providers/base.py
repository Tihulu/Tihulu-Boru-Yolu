"""Provider contracts for Boru Core text-only inference.

A provider is the *only* thing that may talk to a model endpoint.  Results are
typed, bounded and carry an ``evidence_class`` so a synthetic reply can never
be mistaken for a live one.  Raw response bodies, exception text and endpoints
are deliberately **not** stored in results: only safe failure categories cross
a boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

#: Fixed failure categories.  Callers branch on these, never on provider text.
FAILURE_CATEGORIES: Tuple[str, ...] = (
    "timeout",
    "unavailable",
    "unauthorized",
    "rate_limited",
    "model_missing",
    "invalid_response",
    "policy_denied",
    "request_too_large",
    "server_error",
)

ROLES: Tuple[str, ...] = ("system", "user", "assistant")

#: Hard bounds for one chat exchange (Boru Core text-only pilot).
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MESSAGE_CHARS = 32 * 1024
MAX_MESSAGES = 64
MAX_OUTPUT_TOKENS_LIMIT = 8192


class ProviderFailure(Exception):
    """A bounded, categorised provider failure.

    The message is a fixed safe string; provider bodies and endpoints are
    never interpolated, because this text may reach local audit logs.
    """

    def __init__(self, category: str, message: str = "") -> None:
        if category not in FAILURE_CATEGORIES:
            raise ValueError("unknown failure category")
        super().__init__(message or category)
        self.category = category
        self.message = message or category


@dataclass(frozen=True)
class ChatMessage:
    """One conversation turn."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError("unknown message role")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("message content must be a non-empty string")
        if len(self.content) > MAX_MESSAGE_CHARS:
            raise ValueError("message content exceeds the bounded limit")

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatReply:
    """A typed, verified provider reply.

    ``usage`` only contains keys that the provider actually reported; unknown
    usage is absent rather than invented.  ``evidence_class`` is ``simulated``
    for every synthetic provider and ``direct`` only for real observed calls.
    """

    provider: str
    model_id: str
    request_id: str
    content: str
    evidence_class: str
    usage: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.evidence_class not in ("direct", "simulated"):
            raise ValueError("evidence_class must be direct or simulated")
        for name in ("provider", "model_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(name + " must be a non-empty string")
            if len(value) > 128:
                raise ValueError(name + " exceeds the bounded limit")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content must be a non-empty string")
        if len(self.content) > MAX_RESPONSE_BYTES:
            raise ValueError("content exceeds the bounded limit")
        for key, value in dict(self.usage).items():
            if key not in ("input_tokens", "output_tokens", "total_tokens"):
                raise ValueError("unknown usage key")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("usage values must be non-negative integers")
        total = dict(self.usage).get("total_tokens")
        parts = dict(self.usage).get("input_tokens"), dict(self.usage).get("output_tokens")
        if total is not None and all(p is not None for p in parts) and total != parts[0] + parts[1]:
            raise ValueError("inconsistent usage totals")

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "request_id": self.request_id,
            "content": self.content,
            "evidence_class": self.evidence_class,
            "usage": dict(self.usage),
        }


class ChatProvider:
    """Minimal provider interface used by Boru Core."""

    provider: str = ""
    local: bool = True

    def discover(self) -> Tuple[str, ...]:  # pragma: no cover - interface
        raise NotImplementedError

    def chat(
        self,
        model_id: str,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 128,
        timeout: float = 30.0,
    ) -> ChatReply:  # pragma: no cover - interface
        raise NotImplementedError
