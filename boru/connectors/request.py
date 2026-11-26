"""Private, bounded request materialization shared by repository connectors.

Only the resulting immutable tree may be validated or authorized. The wire
conversion creates fresh JSON containers, preserving array/object identity.
"""
from __future__ import annotations

import math
from types import MappingProxyType
from typing import Any, Mapping

from ..errors import ConnectorDenied

MAX_MATERIALIZED_DEPTH = 3
MAX_MATERIALIZED_ITEMS = 64
MAX_MATERIALIZED_NODES = 4096
MAX_MATERIALIZED_STRING = 8192


def freeze_mapping(value: Any) -> Mapping[str, Any]:
    """Read an external mapping once and return a private immutable tree."""
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ConnectorDenied("invalid_body")
    nodes = 0

    def freeze(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if depth > MAX_MATERIALIZED_DEPTH:
            raise ConnectorDenied("body_nested_too_deeply")
        if nodes > MAX_MATERIALIZED_NODES:
            raise ConnectorDenied("body_too_large")
        if isinstance(item, Mapping):
            result = {}
            for index, (key, child) in enumerate(item.items()):
                if index >= MAX_MATERIALIZED_ITEMS:
                    raise ConnectorDenied("body_too_large")
                if type(key) is not str or len(key) > 512 or key in result:
                    raise ConnectorDenied("unsafe_body_key")
                result[key] = freeze(child, depth + 1)
            return MappingProxyType(result)
        if isinstance(item, (list, tuple)):
            result = []
            for index, child in enumerate(item):
                if index >= MAX_MATERIALIZED_ITEMS:
                    raise ConnectorDenied("body_too_large")
                result.append(freeze(child, depth + 1))
            return tuple(result)
        if type(item) is str:
            if len(item) > MAX_MATERIALIZED_STRING:
                raise ConnectorDenied("body_value_too_large")
            return item
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        raise ConnectorDenied("unsafe_body_value")

    return freeze(value, 0)


def wire_body(snapshot: Any) -> Any:
    """Serialize a private snapshot without conflating arrays and objects."""
    if isinstance(snapshot, Mapping):
        return {key: wire_body(value) for key, value in snapshot.items()}
    if isinstance(snapshot, tuple):
        return [wire_body(value) for value in snapshot]
    return snapshot
