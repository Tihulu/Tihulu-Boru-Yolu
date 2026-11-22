"""Direct Jan (OpenAI-compatible) provider for text-only Boru tasks.

Jan's local API server can be configured to proxy *remote* providers and to
execute MCP tools server-side, so a loopback URL alone does **not** prove a
model is local.  This provider therefore requires:

* an explicit, non-empty allowlist of local model IDs (never discovered from
  the endpoint, which may include remote entries);
* ``tool_execution_disabled=True`` asserted by the operator, matching the
  documented Jan setting;
* a numeric loopback endpoint, so DNS rebinding and proxy redirection cannot
  silently redirect a request; and
* ``tool_choice="none"`` plus no tool definitions in the request body.

Nothing here authenticates the operator, authorises Shell use, or proves a
security boundary; it is a bounded text transport.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .base import (
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    ChatMessage,
    ChatProvider,
    ChatReply,
    ProviderFailure,
)


class JanProvider(ChatProvider):
    """Direct OpenAI-compatible chat completions against Jan."""

    provider = "jan"
    local = True
    #: Class-level defaults so the shared helpers also work for an instance
    #: built for cross-provider reuse (see CloudProvider): a reused instance
    #: must never raise an untyped AttributeError on a shared attribute.
    model_response_is_path = False
    allow_discovery = False

    def __init__(
        self,
        base_url: str,
        *,
        local_model_ids: Sequence[str],
        tool_execution_disabled: bool,
        api_prefix: str = "/v1",
        allow_discovery: bool = False,
        model_response_is_path: bool = False,
    ) -> None:
        if not isinstance(allow_discovery, bool):
            raise ValueError("allow_discovery must be a boolean")
        if not isinstance(model_response_is_path, bool):
            raise ValueError("model_response_is_path must be a boolean")
        self.allow_discovery = allow_discovery
        # Jan may report the on-disk model path instead of the model ID. This
        # opt-in keeps identity verification strict: a response is accepted
        # only when it equals the requested ID or contains "/<id>/" in a path.
        # The path itself is never stored or returned.
        self.model_response_is_path = model_response_is_path
        if tool_execution_disabled is not True:
            raise ValueError("tool_execution_disabled must be explicitly True")
        allowlist = tuple(local_model_ids or ())
        if not allowlist:
            raise ValueError("an explicit local model allowlist is required")
        for model_id in allowlist:
            if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 128:
                raise ValueError("model IDs must be non-empty bounded strings")
        if len(set(allowlist)) != len(allowlist):
            raise ValueError("duplicate model IDs in allowlist")
        self._host, self._port, self._tls, self._path, self._prefix = self._parse_endpoint(
            base_url, api_prefix
        )
        self._allowlist = allowlist

    # -- endpoint validation -------------------------------------------------
    @staticmethod
    def _parse_endpoint(base_url: str, api_prefix: str) -> Tuple[str, int, bool, str, str]:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        if len(base_url) > 512 or any(c.isspace() for c in base_url):
            raise ValueError("malformed base_url")
        if "\\" in base_url or "@" in base_url.split("//", 1)[-1].split("/", 1)[0]:
            raise ValueError("userinfo is not permitted")
        try:
            parts = urlsplit(base_url)
        except ValueError:
            raise ValueError("malformed base_url")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("credentials, query and fragment are not permitted")
        if parts.scheme not in ("http", "https"):
            raise ValueError("only http and https are supported")
        host = parts.hostname
        if not host:
            raise ValueError("base_url host is required")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError("endpoint host must be a numeric loopback address")
        if not address.is_loopback:
            raise ValueError("endpoint must be loopback; remote endpoints are refused")
        port = parts.port
        if port is None:
            port = 443 if parts.scheme == "https" else 80
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("invalid port")
        prefix = api_prefix.strip("/")
        combined = (parts.path.strip("/") + "/" + prefix).split("/") if prefix else parts.path.strip("/").split("/")
        if any(part in ("", ".", "..") for part in combined):
            raise ValueError("invalid API path or prefix")
        path = parts.path.rstrip("/")
        return host, port, parts.scheme == "https", path, prefix

    # -- provider interface --------------------------------------------------
    def discover(self) -> Tuple[str, ...]:
        """Return the operator-configured allowlist (never the raw inventory)."""
        return self._allowlist

    def health(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Bounded health probe. Never returns remote or model inventory data."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 30:
            raise ProviderFailure("invalid_response", "invalid timeout")
        status, raw = self._exchange("GET", "/" + self._prefix + "/models", None, float(timeout))
        if status != 200:
            raise self._http_failure(status)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderFailure("invalid_response", "provider returned malformed JSON")
        data = payload.get("data") if isinstance(payload, dict) else None
        count = len(data) if isinstance(data, list) else 0
        return {"status": "ok", "models_listed": count}

    def discover_models(self, timeout: float = 10.0) -> Tuple[str, ...]:
        """Opt-in model listing through the supported Jan API.

        Must be enabled explicitly by the operator because a Jan endpoint may
        also serve remote providers; listing models does not make any of them
        authorized. The returned IDs are cross-checked against the configured
        local allowlist, and only allowlisted IDs are reported as usable.
        """
        if self.allow_discovery is not True:
            raise ProviderFailure("policy_denied", "model discovery is not enabled")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 60:
            raise ProviderFailure("invalid_response", "invalid timeout")
        status, raw = self._exchange("GET", "/" + self._prefix + "/models", None, float(timeout))
        if status != 200:
            raise self._http_failure(status)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderFailure("invalid_response", "provider returned malformed JSON")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ProviderFailure("invalid_response", "unexpected model listing")
        found: List[str] = []
        for entry in data[:256]:
            if not isinstance(entry, dict):
                raise ProviderFailure("invalid_response", "unexpected model listing")
            model_id = entry.get("id")
            if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 128:
                raise ProviderFailure("invalid_response", "unexpected model listing")
            if model_id in self._allowlist:
                found.append(model_id)
        if not found:
            raise ProviderFailure("model_missing", "no allowlisted model is present")
        return tuple(found)

    def chat(
        self,
        model_id: str,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 128,
        timeout: float = 30.0,
    ) -> ChatReply:
        if model_id not in self._allowlist:
            raise ProviderFailure("policy_denied", "model is not in the configured allowlist")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS_LIMIT:
            raise ProviderFailure("invalid_response", "invalid max_tokens")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 120:
            raise ProviderFailure("invalid_response", "invalid timeout")
        body = {
            "model": model_id,
            "messages": [m.to_dict() for m in messages],
            "max_tokens": max_tokens,
            "stream": False,
            "tool_choice": "none",
        }
        payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise ProviderFailure("request_too_large", "request exceeds the bounded size")
        status, raw = self._exchange("POST", "/" + self._prefix + "/chat/completions", payload, float(timeout))
        if status != 200:
            raise self._http_failure(status)
        return self._parse_reply(raw, model_id)

    # -- bounded HTTP --------------------------------------------------------
    def _connect(self, remaining: float) -> http.client.HTTPConnection:
        if self._tls:
            return http.client.HTTPSConnection(self._host, self._port, timeout=remaining)
        return http.client.HTTPConnection(self._host, self._port, timeout=remaining)

    def _exchange_headers(self, method: str, path: str, payload: Optional[bytes], timeout: float,
                          headers: Dict[str, str]) -> Tuple[int, bytes]:
        """Bounded exchange with explicit headers (used by cloud providers too)."""
        deadline = time.monotonic() + timeout
        conn = self._connect(max(deadline - time.monotonic(), 0.05))
        try:
            conn.request(method, path, body=payload, headers=headers)
            if conn.sock is not None:
                conn.sock.settimeout(max(deadline - time.monotonic(), 0.05))
            response = conn.getresponse()
            chunks: List[bytes] = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderFailure("timeout", "provider deadline exceeded")
                if conn.sock is not None:
                    conn.sock.settimeout(max(remaining, 0.05))
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ProviderFailure("request_too_large", "response exceeds the bounded size")
                chunks.append(chunk)
            return response.status, b"".join(chunks)
        except ProviderFailure:
            raise
        except socket.timeout:
            raise ProviderFailure("timeout", "provider read timed out")
        except (socket.error, OSError):
            raise ProviderFailure("unavailable", "provider connection failed")
        except http.client.HTTPException:
            raise ProviderFailure("unavailable", "provider protocol error")
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

    def _exchange(self, method: str, path: str, payload: Optional[bytes], timeout: float) -> Tuple[int, bytes]:
        """Perform one bounded request/response exchange.

        The deadline covers the whole exchange, not each read, so a slow-drip
        reply cannot stall Boru Core indefinitely.  No redirect is followed and
        no environment proxy is consulted.
        """
        deadline = time.monotonic() + timeout
        conn = self._connect(max(deadline - time.monotonic(), 0.05))
        try:
            conn.request(method, path, body=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
            if conn.sock is not None:
                conn.sock.settimeout(max(deadline - time.monotonic(), 0.05))
            response = conn.getresponse()
            chunks: List[bytes] = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderFailure("timeout", "provider deadline exceeded")
                if conn.sock is not None:
                    conn.sock.settimeout(max(remaining, 0.05))
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ProviderFailure("request_too_large", "response exceeds the bounded size")
                chunks.append(chunk)
            return response.status, b"".join(chunks)
        except ProviderFailure:
            raise
        except socket.timeout:
            raise ProviderFailure("timeout", "provider read timed out")
        except (socket.error, OSError):
            raise ProviderFailure("unavailable", "provider connection failed")
        except http.client.HTTPException:
            raise ProviderFailure("unavailable", "provider protocol error")
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

    @staticmethod
    def _http_failure(status: int) -> ProviderFailure:
        if status in (401, 403):
            return ProviderFailure("unauthorized", "provider rejected credentials")
        if status == 404:
            return ProviderFailure("model_missing", "provider has no such model")
        if status == 429:
            return ProviderFailure("rate_limited", "provider rate limit reached")
        if status == 408:
            return ProviderFailure("timeout", "provider timed out")
        if 500 <= status < 600:
            return ProviderFailure("server_error", "provider server error")
        if 300 <= status < 400:
            return ProviderFailure("policy_denied", "redirects are not followed")
        return ProviderFailure("invalid_response", "unexpected provider status")

    def _parse_reply(self, raw: bytes, model_id: str) -> ChatReply:
        def object_pairs(pairs):
            result: Dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        try:
            text = raw.decode("utf-8")
            data = json.loads(text, object_pairs_hook=object_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite")))
        except (UnicodeDecodeError, ValueError):
            raise ProviderFailure("invalid_response", "provider returned malformed JSON")
        if not isinstance(data, dict):
            raise ProviderFailure("invalid_response", "unexpected provider payload")
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ProviderFailure("invalid_response", "unexpected provider payload")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderFailure("invalid_response", "unexpected provider payload")
        if choice.get("tool_calls") or choice.get("function_call"):
            raise ProviderFailure("policy_denied", "provider attempted a tool call")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderFailure("invalid_response", "unexpected provider payload")
        if message.get("tool_calls") or message.get("function_call"):
            raise ProviderFailure("policy_denied", "provider attempted a tool call")
        if message.get("role") not in (None, "assistant"):
            raise ProviderFailure("invalid_response", "unexpected provider payload")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderFailure("invalid_response", "empty provider content")
        if len(content) > MAX_RESPONSE_BYTES:
            raise ProviderFailure("request_too_large", "content exceeds the bounded size")
        if not self._model_matches(data.get("model"), model_id):
            raise ProviderFailure("invalid_response", "provider returned a different model")
        request_id = data.get("id")
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise ProviderFailure("invalid_response", "missing provider request identifier")
        return ChatReply(
            provider=self.provider,
            model_id=model_id,
            request_id=request_id,
            content=content,
            evidence_class="direct",
            usage=self._parse_usage(data.get("usage")),
        )

    def _model_matches(self, reported: Any, model_id: str) -> bool:
        """Strict identity check that tolerates a documented local-path reply."""
        if not isinstance(reported, str) or not reported.strip():
            return False
        if reported == model_id:
            return True
        if self.model_response_is_path and len(reported) <= 512 and "/{}/".format(model_id) in reported:
            return True
        return False

    @staticmethod
    def _parse_usage(usage: Any) -> Dict[str, int]:
        if usage is None:
            return {}
        if not isinstance(usage, dict):
            raise ProviderFailure("invalid_response", "unexpected usage shape")
        mapping = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens", "total_tokens": "total_tokens"}
        parsed: Dict[str, int] = {}
        for source, target in mapping.items():
            if source not in usage:
                continue
            value = usage[source]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProviderFailure("invalid_response", "invalid usage value")
            parsed[target] = value
        if {"input_tokens", "output_tokens", "total_tokens"} <= set(parsed) and parsed["total_tokens"] != parsed["input_tokens"] + parsed["output_tokens"]:
            raise ProviderFailure("invalid_response", "inconsistent usage totals")
        return parsed
