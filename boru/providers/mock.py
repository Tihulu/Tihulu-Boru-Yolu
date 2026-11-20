"""Deterministic in-process mock provider.

Used by CI and offline demos only.  Every reply is ``simulated`` evidence and
can therefore never reach ``DONE`` as a live result: ``BoruCore`` keeps it in
``REVIEW`` until the owner explicitly accepts it.
"""
from __future__ import annotations

import zlib
from typing import Sequence

from .base import ChatMessage, ChatProvider, ChatReply, ProviderFailure

MODEL_ID = "mock-text-v1"


class MockProvider(ChatProvider):
    """Offline, deterministic, zero I/O provider."""

    provider = "mock"
    local = True

    def discover(self) -> tuple:
        return (MODEL_ID,)

    def chat(
        self,
        model_id: str,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 128,
        timeout: float = 30.0,
    ) -> ChatReply:
        if model_id != MODEL_ID:
            raise ProviderFailure("model_missing", "unknown mock model")
        turns = [m for m in messages if m.role in ("user", "assistant")]
        if not turns:
            raise ProviderFailure("invalid_response", "no conversation turns")
        last = turns[-1]
        digest = zlib.crc32("{}:{}:{}".format(last.role, len(turns), last.content).encode("utf-8"))
        request_id = "mock-{}".format(digest & 0xFFFFFFFFFFFF)
        reply = "mock-ack:{}".format(last.content[:64])
        return ChatReply(
            provider=self.provider,
            model_id=model_id,
            request_id=request_id,
            content=reply,
            evidence_class="simulated",
            usage={"input_tokens": 8, "output_tokens": 8, "total_tokens": 16},
        )
