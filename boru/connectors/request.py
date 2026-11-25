"""Shared bounded request materialization. No caller-owned objects survive.

Objects are read once into private mapping proxies; arrays are distinct
immutable tuples. Validate and authorize this exact tree, then thaw it only
at the transport boundary. No credentials are stored here.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping

from ..errors import ConnectorDenied

MAX_DEPTH = 3
MAX_ITEMS = 32
MAX_TEXT = 4096


def freeze(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise ConnectorDenied("body_nested_too_deeply")
    if isinstance(value, Mapping):
        copied = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_ITEMS:
                raise ConnectorDenied("body_too_large")
            if type(key) is not str or not key or len(key) > 256 or key in copied:
                raise ConnectorDenied("unsafe_body_key")
            copied[key] = freeze(item, depth + 1)
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        items = []
        for index, item in enumerate(value):
            if index >= MAX_ITEMS:
                raise ConnectorDenied("body_too_large")
            items.append(freeze(item, depth + 1))
        return tuple(items)
    if type(value) is str:
        if len(value) > MAX_TEXT:
            raise ConnectorDenied("body_value_too_large")
        return value
    if type(value) is int:
        if not -(2**53) <= value <= 2**53:
            raise ConnectorDenied("body_value_out_of_range")
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ConnectorDenied("unsafe_body_value")
        return value
    if value is None or type(value) is bool:
        return value
    raise ConnectorDenied("unsafe_body_value")


def freeze_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ConnectorDenied("invalid_body")
    try:
        return freeze(value)
    except ConnectorDenied:
        raise
    except (TypeError, ValueError, KeyError, RuntimeError):
        # A changing or malformed Mapping cannot reach the transport.
        raise ConnectorDenied("invalid_body") from None


def wire_body(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: wire_body(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [wire_body(item) for item in value]
    return value


@dataclass(frozen=True)
class PreparedRequest:
    slots: Mapping[str, str]
    body: Mapping[str, Any]


def prepare(grant, operation, payload, body, *, method, path,
            default_method, contracts) -> PreparedRequest:
    from .scope import check_call, check_write_body
    captured_payload = freeze_mapping(payload)
    captured_body = freeze_mapping(body)
    slots = check_call(grant, operation, captured_payload, method=method,
                       path=path, default_method=default_method)
    check_write_body(grant, operation, captured_body, captured_payload, contracts)
    return PreparedRequest(MappingProxyType(slots), captured_body)
