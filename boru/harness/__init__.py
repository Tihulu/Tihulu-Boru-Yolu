"""Boru Harness — optional, disabled-by-default local observability & policy.

This package is **not** an authorization surface. Every restricted action still
routes through Boru Core, the broker and the sandbox. The harness:

* `shell_policy` — a pure, fail-closed command deny floor for the
  `run_synthetic_command` authorization decision (ADR 0006);
* `tui` — a read-only live observability console over existing primitives;
* `verify` — a read-only, post-hoc claim audit over durable state, which
  reports unbacked successes, unexplained failures, unknown states, unsafe
  ledger rows and an over-bound store, and repairs nothing;
* `review` — an interactive owner-review console that routes every accept/reject
  through the existing `BoruCore.review()` path, is fail-closed on EOF or an
  unrecognised key, and decides nothing without an explicit owner choice.

Nothing here starts a provider call, widens a policy axis, or releases private
data. See `docs/ADRS/0006-harness-and-observability.md`.
"""
from __future__ import annotations

__all__ = ["shell_policy", "tui", "verify", "review"]
