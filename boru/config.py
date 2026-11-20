"""Versioned runtime configuration for Boru Core.

Safety defaults mirror ADR-0002/ADR-0004: ``LOCAL_ONLY`` inference,
``LOCAL_ISOLATED`` execution, ``MINIMUM_NECESSARY`` disclosure, no network, no
autostart, no credentials.  An endpoint or model allowlist must be stated
explicitly; nothing is discovered or inferred from the host.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigurationError
from .policy import Policy

CONFIG_VERSION = 1
QUEUE_LIMIT = 16
MAX_RECORDS = 1024
REQUEST_TIMEOUT = 30.0
MAX_OUTPUT_TOKENS = 256

_SUPPORTED_CAPABILITIES = ("text",)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(label + " must be a boolean")
    return value


def _int(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigurationError(label + " must be an integer between {} and {}".format(low, high))
    return value


def _positive_float(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= float(value) <= high:
        raise ConfigurationError(label + " must be a finite number between {} and {}".format(low, high))
    return float(value)


def _text(value: Any, label: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ConfigurationError(label + " must be a bounded non-empty string")
    return value


@dataclass(frozen=True)
class ProviderConfig:
    """Bounded description of one configured provider.

    ``api_key_env`` names an environment variable; credential values are never
    stored in configuration, logs or prompts.
    """

    kind: str
    endpoint: Optional[str] = None
    local_model_ids: Tuple[str, ...] = ()
    tool_execution_disabled: bool = True
    allow_http: bool = False
    api_key_env: Optional[str] = None
    #: Opt-in model listing through the provider API. Disabled by default
    #: because a local endpoint may also serve remote providers.
    allow_discovery: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.kind not in ("mock", "jan", "cloud"):
            errors.append("unknown provider kind")
        if self.kind == "cloud":
            if not isinstance(self.endpoint, str) or not self.endpoint.strip():
                errors.append("cloud provider requires an explicit https endpoint")
            elif not self.endpoint.strip().lower().startswith("https://") and not self.allow_http:
                errors.append("cloud endpoints require https unless http is explicitly allowed")
            if not self.local_model_ids:
                errors.append("cloud provider requires an explicit model allowlist")
        if self.kind != "cloud" and self.tool_execution_disabled is not True:
            errors.append("tool_execution_disabled must be True; Boru Core text-only transport refuses remote tool execution")
        if not isinstance(self.allow_http, bool):
            errors.append("allow_http must be a boolean")
        if not isinstance(self.allow_discovery, bool):
            errors.append("allow_discovery must be a boolean")
        if self.api_key_env is not None and (
            not isinstance(self.api_key_env, str) or not self.api_key_env.strip() or len(self.api_key_env) > 64
        ):
            errors.append("api_key_env must be a bounded environment variable name")
        if self.kind == "jan":
            if not isinstance(self.endpoint, str) or not self.endpoint.strip():
                errors.append("Jan provider requires an explicit endpoint")
            if not self.local_model_ids:
                errors.append("Jan provider requires an explicit local model allowlist")
            if not _is_loopback_endpoint(self.endpoint):
                errors.append("Jan provider endpoint must be a numeric loopback address")
        return errors


def _is_loopback_endpoint(endpoint: Any) -> bool:
    """Cheap, dependency-free loopback check used only for fail-fast config."""
    if not isinstance(endpoint, str):
        return False
    try:
        from urllib.parse import urlsplit
        import ipaddress

        parts = urlsplit(endpoint.strip())
        return ipaddress.ip_address(parts.hostname).is_loopback
    except Exception:
        return False


@dataclass(frozen=True)
class CoreConfig:
    """Complete runtime configuration."""

    version: int = CONFIG_VERSION
    policy: Policy = field(default_factory=Policy)
    queue_limit: int = QUEUE_LIMIT
    max_records: int = MAX_RECORDS
    request_timeout: float = REQUEST_TIMEOUT
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    providers: Tuple[ProviderConfig, ...] = ()
    description: str = ""
    cooldown_seconds: float = 60.0
    max_context_chars: int = 32 * 1024

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.description, str) or len(self.description) > 512:
            errors.append("description must be a bounded string")
        if self.version != CONFIG_VERSION:
            errors.append("unsupported configuration version")
        errors.extend(self.policy.validate())
        for name, value, low, high in (
            ("queue_limit", self.queue_limit, 1, 256),
            ("max_records", self.max_records, 1, 100000),
            ("max_output_tokens", self.max_output_tokens, 1, 8192),
        ):
            errors.extend(_int_errors(value, name, low, high))
        errors.extend(_float_errors(self.request_timeout, "request_timeout", 0.1, 120.0))
        if self.max_records < self.queue_limit:
            errors.append("max_records must not be smaller than queue_limit")
        errors.extend(_float_errors(self.cooldown_seconds, "cooldown_seconds", 1.0, 3600.0))
        errors.extend(_int_errors(self.max_context_chars, "max_context_chars", 256, 1 << 20))
        if not self.providers:
            errors.append("at least one provider must be configured")
        for provider in self.providers:
            errors.extend(provider.validate())
        return errors

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ConfigurationError("; ".join(sorted(set(errors))))

    @classmethod
    def from_dict(cls, raw: Any) -> "CoreConfig":
        if not isinstance(raw, dict):
            raise ConfigurationError("configuration must be an object")
        allowed = {"version", "policy", "queue_limit", "max_records", "request_timeout",
                   "max_output_tokens", "providers", "description", "cooldown_seconds",
                   "max_context_chars"}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ConfigurationError("unknown configuration field")
        if len(json.dumps(raw, default=str, sort_keys=True)) > 256 * 1024:
            raise ConfigurationError("configuration exceeds the bounded size")
        policy_raw = raw.get("policy", {})
        if not isinstance(policy_raw, dict):
            raise ConfigurationError("policy must be an object")
        policy_fields = {
            "optimization_mode", "inference_scope", "execution_profile", "disclosure_policy",
            "cloud_shell_enabled", "cloud_shell_sandbox_required", "cloud_shell_live_consent_required",
            "raw_tool_output_to_cloud", "recipient_bound_consent_required", "max_result_fields",
            "max_agents", "max_retries", "cloud_fallback_enabled",
        }
        unknown_policy = sorted(set(policy_raw) - policy_fields)
        if unknown_policy:
            raise ConfigurationError("unknown policy field")
        policy = Policy(**policy_raw)
        providers_raw = raw.get("providers", [])
        if not isinstance(providers_raw, list) or not providers_raw:
            raise ConfigurationError("providers must be a non-empty list")
        providers = []
        for entry in providers_raw:
            if not isinstance(entry, dict):
                raise ConfigurationError("provider entries must be objects")
            unknown_entry = sorted(set(entry) - {"kind", "endpoint", "local_model_ids",
                                                 "tool_execution_disabled", "allow_http", "api_key_env",
                                                 "allow_discovery"})
            if unknown_entry:
                raise ConfigurationError("unknown provider field")
            models = entry.get("local_model_ids", [])
            if not isinstance(models, list):
                raise ConfigurationError("local_model_ids must be a list")
            for model in models:
                _text(model, "model id", 128)
            providers.append(
                ProviderConfig(
                    kind=_text(entry.get("kind", ""), "provider kind"),
                    endpoint=entry.get("endpoint"),
                    local_model_ids=tuple(models),
                    tool_execution_disabled=_bool(entry.get("tool_execution_disabled", True), "tool_execution_disabled"),
                    allow_http=_bool(entry.get("allow_http", False), "allow_http"),
                    api_key_env=entry.get("api_key_env"),
                    allow_discovery=_bool(entry.get("allow_discovery", False), "allow_discovery"),
                )
            )
        config = cls(
            version=_int(raw.get("version", CONFIG_VERSION), "version", 1, 1),
            policy=policy,
            queue_limit=_int(raw.get("queue_limit", QUEUE_LIMIT), "queue_limit", 1, 256),
            max_records=_int(raw.get("max_records", MAX_RECORDS), "max_records", 1, 100000),
            request_timeout=_positive_float(raw.get("request_timeout", REQUEST_TIMEOUT), "request_timeout", 0.1, 120.0),
            max_output_tokens=_int(raw.get("max_output_tokens", MAX_OUTPUT_TOKENS), "max_output_tokens", 1, 8192),
            providers=tuple(providers),
            description=_text(raw.get("description", ""), "description", 512) if raw.get("description") else "",
            cooldown_seconds=_positive_float(raw.get("cooldown_seconds", 60.0), "cooldown_seconds", 1.0, 3600.0),
            max_context_chars=_int(raw.get("max_context_chars", 32 * 1024), "max_context_chars", 256, 1 << 20),
        )
        config.assert_valid()
        return config


    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "policy": self.policy.as_dict(),
            "queue_limit": self.queue_limit,
            "max_records": self.max_records,
            "request_timeout": self.request_timeout,
            "max_output_tokens": self.max_output_tokens,
            "providers": [
                {"kind": p.kind, "endpoint": p.endpoint, "local_model_ids": list(p.local_model_ids),
                 "tool_execution_disabled": p.tool_execution_disabled, "allow_http": p.allow_http,
                 "api_key_env": p.api_key_env, "allow_discovery": p.allow_discovery}
                for p in self.providers
            ],
            "description": self.description,
            "cooldown_seconds": self.cooldown_seconds,
            "max_context_chars": self.max_context_chars,
        }

    @classmethod
    def from_file(cls, path: str) -> "CoreConfig":
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("configuration is not valid JSON")
        except OSError:
            raise ConfigurationError("configuration cannot be read")
        return cls.from_dict(raw)


def _int_errors(value: Any, label: str, low: int, high: int) -> List[str]:
    try:
        _int(value, label, low, high)
    except ConfigurationError as exc:
        return [str(exc)]
    return []


def _float_errors(value: Any, label: str, low: float, high: float) -> List[str]:
    try:
        _positive_float(value, label, low, high)
    except ConfigurationError as exc:
        return [str(exc)]
    return []


def default_config() -> CoreConfig:
    """Offline default: mock provider only, no network, no state file."""
    return CoreConfig(providers=(ProviderConfig(kind="mock"),))
