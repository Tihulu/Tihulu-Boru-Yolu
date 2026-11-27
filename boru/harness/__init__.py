"""Boru Harness — optional, disabled-by-default local observability & policy.

This package is **not** an authorization surface. Every restricted action still
routes through Boru Core, the broker and the sandbox. The harness:

* `shell_policy` — a pure, fail-closed command deny floor for the
  `run_synthetic_command` authorization decision (ADR 0005);
* `tui` — a read-only live observability console over existing primitives.

Nothing here starts a provider call, widens a policy axis, or releases private
data. See `docs/ADRS/0005-harness-and-observability.md`.
"""
from __future__ import annotations

__all__ = ["shell_policy", "tui"]
