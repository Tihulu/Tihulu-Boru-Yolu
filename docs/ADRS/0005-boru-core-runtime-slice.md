# ADR-0005: Boru Core runtime slice — stdlib Python, offline-first, no TIHULU-AUTO

- Status: **Proposed — implementation pilot; owner review required**
- Date: 2026-11-20
- Related: ADR-0002 (Shell profiles), ADR-0003 (Boru Core independence), ADR-0004 (preserved modes and privacy), issue #12, issue #13

## Context

The repository baseline contained architecture, ADRs 0001–0004, a sample
configuration and dependency-free static checks, but **no executable code**.
P1 of `docs/CODEX_EXECUTION_PLAYBOOK.md` requires a native, independently
installable Boru Core minimum: typed contracts, deterministic task states,
bounded work, a mock provider for CI, and a *direct* Jan text-only connector.

The playbook names Rust + TypeScript as a candidate stack, but also requires
an ADR and a check of installed constraints before committing to it. The host
already runs the CI baseline on Python 3 and the static checks are Python;
adding a Rust toolchain dependency would create an install requirement for a
slice that must run offline, unprivileged and reviewable today.

## Decision

Implement this P1 slice in **Python 3.12+ standard library only, zero
third-party dependencies**:

- `boru/types.py` — `TaskEnvelope` / `AgentResult` typed contracts.
- `boru/policy.py` — the four orthogonal policy axes with safe defaults.
- `boru/state.py`, `boru/queue.py` — deterministic state machine and bounded,
  replay-protected queue.
- `boru/store.py` — local SQLite task state, owner-created state directory.
- `boru/providers/` — `MockProvider` (simulated evidence) and `JanProvider`
  (direct, text-only, loopback, tool-execution-disabled transport).
- `boru/core.py`, `boru/cli.py` — orchestrator and `python -m boru` CLI.

"Native" here means **Boru's own logic, independent of TIHULU-AUTO**; it does
not claim a compiled artifact. A Rust core/broker remains a future, separate
ADR if the measurement warrants it; nothing in this slice blocks that.

## Safety defaults

`LOCAL_ONLY` inference, `LOCAL_ISOLATED` execution, `MINIMUM_NECESSARY`
disclosure, loopback-only endpoints, no autostart, no credentials, no network
unless an endpoint is explicitly configured, and no host Shell of any kind.
A completed model reply reaches `REVIEW`; `DONE` requires an explicit local
owner review, and the evidence class is preserved so a simulated result is
never relabelled as live.

## Consequences

- P1 is reviewable and runnable on Pop!_OS/Ubuntu without installing a
  toolchain or a service, which keeps rollback trivial (delete the state
  directory).
- The Python slice is a pilot, not a final platform decision; a Rust
  broker/Privacy Bridge (P5) is still a candidate and may reuse these
  contracts through the versioned schemas.
- Type optimization modes are preserved as contract data; mode-dependent
  *weighted* routing is **not** implemented in this slice and remains HOLD
  for P3 rather than being simulated.

## Explicit non-claims

- No live Jan inference, no OAuth, no cloud inference, no Shell tool, no
  sandbox, no install acceptance, no security boundary and no Linux
  certification is claimed by this ADR. The live Jan 3-turn pilot is
  documented in `docs/JAN_PILOT.md` and remains HOLD until an approved run.

## Rollback

Remove the development branch and, if one was created, the dedicated
`--state-dir` directory. Nothing else on the host is touched: no global
configuration, no service, no Jan/OpenCode data.
