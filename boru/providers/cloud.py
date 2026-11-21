"""Generic OpenAI-compatible *cloud* provider (P7 source slice).

Design rules this transport enforces:

* HTTPS-only unless the operator explicitly permits HTTP for a pinned host;
* an explicit allowlist of model IDs the owner authorized;
* credentials are **never** stored in configuration or logs: only an
  environment-variable *name* is configured and the value is read at request
  time (ADR: OS keyring / vault is a P5 follow-up);
* identity is not inference: a successful call records
  ``MODEL_TEST_PASSED`` for that model only, and never for the account.

This is transport code.  It does not decide whether a recipient may receive
data — the Privacy Bridge gate in `boru/privacy.py` does — and no live
provider call is made by this repository.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Sequence, Tuple

from .base import ChatMessage, ChatProvider, ChatReply, ProviderFailure

#: Honest connection states.  A configured endpoint is not an authentication.
CONNECTION_STATES: Tuple[str, ...] = (
    "configured",
    "authenticated",
    "model_discovered",
    "model_test_passed",
    "rate_limited",
    "unavailable",
    "unauthorized",
)


class CloudProvider(ChatProvider):
    """Official OpenAI-compatible chat completions for a cloud account."""

    provider = "cloud"
    local = False

    def __init__(
        self,
        provider_name: str,
        base_url: str,
        *,
        model_ids: Sequence[str],
        api_key_env: Optional[str] = None,
        allow_http: bool = False,
    ) -> None:
        if not isinstance(provider_name, str) or not provider_name.strip() or len(provider_name) > 64:
            raise ValueError("provider_name must be a bounded non-empty string")
        if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 512:
            raise ValueError("base_url must be a bounded non-empty string")
        if any(c.isspace() for c in base_url) or "\\" in base_url or "@" in base_url.split("//", 1)[-1].split("/", 1)[0]:
            raise ValueError("malformed base_url")
        try:
            from urllib.parse import urlsplit
            
            parts = urlsplit(base_url)
        except ValueError:
            raise ValueError("malformed base_url")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("credentials, query and fragment are not permitted")
        if parts.scheme == "https":
            self._tls = True
        elif parts.scheme == "http" and allow_http is True:
            self._tls = False
        else:
            raise ValueError("cloud endpoints require https (set allow_http only for an owner-approved host)")
        if not parts.hostname:
            raise ValueError("base_url host is required")
        self._host = parts.hostname
        self._port = parts.port or (443 if self._tls else 80)
        self._path = parts.path.rstrip("/")
        self._tls_flag = self._tls
        self._transport = None
        self._allowlist = tuple(model_ids or ())
        if not self._allowlist or any(not m.strip() or len(m) > 128 for m in self._allowlist or ()):
            raise ValueError("an explicit model allowlist is required")
        if len(set(self._allowlist)) != len(self._allowlist):
            raise ValueError("duplicate model IDs in allowlist")
        if api_key_env is not None and (not isinstance(api_key_env, str) or not api_key_env.strip() or len(api_key_env) > 64):
            raise ValueError("api_key_env must be a bounded environment variable name")
        self.api_key_env = api_key_env

    # -- identity vs inference ------------------------------------------------
    def connection_state(self) -> str:
        """Report what is currently known, without inventing an entitlement.

        ``configured`` means the owner declared the endpoint and models; no
        credential or model call has been observed.  ``authenticated`` only
        means a credential is present — it is not an inference entitlement.
        """
        if self._api_key():
            return "authenticated"
        return "configured"

    def _api_key(self) -> Optional[str]:
        if not self.api_key_env:
            return None
        value = os.environ.get(self.api_key_env)
        if not value:
            return None
        return value.strip()

    def discover(self) -> Tuple[str, ...]:
        return self._allowlist

    def chat(self, model_id: str, messages: Sequence[ChatMessage], *, max_tokens: int = 128,
             timeout: float = 30.0) -> ChatReply:
        if model_id not in self._allowlist:
            raise ProviderFailure("policy_denied", "model is not in the configured allowlist")
        key = self._api_key()
        if self.api_key_env and not key:
            raise ProviderFailure("unauthorized", "credential environment variable is not set")
        body = {
            "model": model_id,
            "messages": [m.to_dict() for m in messages],
            "max_tokens": max_tokens,
            "stream": False,
            "tool_choice": "none",
        }
        payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
        if len(payload) > 64 * 1024:
            raise ProviderFailure("request_too_large", "request exceeds the bounded size")
        status, raw = self._exchange("POST", self._path + "/chat/completions", payload, float(timeout), key)
        if status != 200:
            raise self._http_failure(status)
        return self._parse_reply(raw, model_id)

    # -- bounded HTTP --------------------------------------------------------
    def _exchange(self, method: str, path: str, payload: Optional[bytes], timeout: float,
                  api_key: Optional[str], transport=None):
        """One bounded exchange; ``transport`` is injected by tests only."""
        if transport is not None:
            return transport(method, path, payload, timeout, api_key)
        from .jan import JanProvider

        exchanger = JanProvider.__new__(JanProvider)
        exchanger._host, exchanger._port, exchanger._tls = self._host, self._port, self._tls_flag
        exchanger._prefix = self._path.strip("/") or "v1"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        status, raw = exchanger._exchange_headers(method, path, payload, timeout, headers)
        return status, raw

    @staticmethod
    def _http_failure(status: int) -> ProviderFailure:
        from .jan import JanProvider

        return JanProvider._http_failure(status)

    def _parse_reply(self, raw: bytes, model_id: str) -> ChatReply:
        from .jan import JanProvider

        exchanger = JanProvider.__new__(JanProvider)
        reply = exchanger._parse_reply(raw, model_id)
        reply = ChatReply(
            provider=self.provider,
            model_id=model_id,
            request_id=reply.request_id,
            content=reply.content,
            evidence_class="direct",
            usage=dict(reply.usage),
        )
        return reply
