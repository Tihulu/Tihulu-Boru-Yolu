# ADR 0005 — Native Boru Harness & Observability (evaluation-driven)

- Status: accepted (design + first vertical slice)
- Date: 2026-11-27
- Relates to: ADR 0003 (native Boru Core independence), ADR 0004 (four independent axes, preserve modes and privacy)

## Context

Gate 1 is code-complete (796 tests, CI green). The missing product surface is a
local **harness**: live observability of agents/leases/budgets/approvals and a
hardened command-decision floor. Three external projects were evaluated for
adoption rather than reinvention:

1. `OrcunSamiTandogan/agent-orchestration-setup` — a desktop launcher bound to
   the Turkish e-Devlet **EVREN** identity service and NVIDIA/DeepSeek
   providers. It is an end-user desktop app and setup prompts, **not** a
   reusable library, and its provider path is region-locked. **Not integrable
   as a dependency.** Its transferable ideas: a guided first-run verification
   checklist and a multi-pane workspace layout.
2. `ojuschugh1/OpenHawk` (Rust) — a local-first "Agent OS": CoW filesystem
   snapshots + undo, an AES-256-GCM secrets vault, a JSON-RPC bus, per-agent
   permission sandboxing, a TUI dashboard, air-gapped mode, and claim
   verification. Architecturally the closest match to Boru's broker/sandbox/
   scheduler split, **but written in Rust**.
3. `shoaibyazdani/leo-agent` (Python) — provider-independent, local-first:
   TUI chat (`leo tui`), loopback dashboard+API (`leo serve`), interactive
   approval gates with audit, a shell **deny-policy** floor (`smart|manual|off`
   plus hardline `deny_commands`), and "external content is untrusted data,
   never instructions". Same language/stack as Boru Core.

## Decision

Build a **native `boru/harness/`** layer inside Boru Core. Do **not** adopt any
external project as a runtime dependency and do **not** become a wrapper: ADR
0003 requires a native, independent core. LEO and OpenHawk are used as
**design references only**; their patterns are re-implemented in Python inside
Boru's own authorization model.

The harness is **optional and disabled by default**. It introduces **no new
authorization surface**: every restricted action still routes through Boru
Core, the broker and the sandbox, and the harness cannot widen a policy axis,
start a provider call, or release private data — exactly the constraint already
stated in `boru/dashboard.py`.

## First vertical slice

1. `boru/harness/shell_policy.py` — a pure, fail-closed **command deny floor**
   for the `run_synthetic_command` authorization decision (LEO's
   `deny_commands` + hardline patterns; OpenHawk's manifest permission idea).
   It is a *decision* function only: it never executes anything and hardens the
   existing sandbox decision path ahead of any future execution path.
2. `boru/harness/verify.py` — a **read-only, post-hoc claim audit** (OpenHawk
   `claimcheck` / LEO audited-approvals pattern). Boru enforces its invariants
   at transition time; this answers the owner's different question *after the
   fact*: "does the durable state I am reading actually back the claims it
   makes?" It reports, and never repairs, a success with no attempt evidence, a
   failure with no reason, an unknown state name, a ledger row carrying a path or
   URL, and an over-bound store. Every reported subject passes through the same
   `boru.audit.sanitize_identifier` used by the ledger, so a hostile `task_id`
   cannot launder a path into a report — a finding pinned by test.
3. `boru/harness/tui.py` — a **read-only** live observability console over a
   pure, testable snapshot function (OpenHawk HawkEye / LEO `leo tui`
   pattern). `snapshot_from_core(core)` wires it to a real `BoruCore` and reads
   only bounded public state: the four axes from `core.policy`, providers by
   kind and ordinal only (never an endpoint, key-name or model id), task and
   review-queue depths from `core.store`, and the rejection ledger tail as
   reasons only. It performs no dispatch, no provider call and no review, and a
   missing/unreadable state directory degrades to an empty view rather than
   blocking an operator.

## Consequences

- Positive: local-first observability and a hardened command-decision floor
  without a new dependency, a new network surface, or a new authorization path.
- Positive: preserves the four independent axes, LOCAL_ONLY / LOCAL_ISOLATED /
  MINIMUM_NECESSARY defaults and all HOLD gates.
- Negative/held: an encrypted at-rest secrets vault is **already provided** by
  `boru/auth/` (the `connect`/`accounts`/`disconnect` token vault), so it is not
  re-invented here. CoW snapshot/undo, and interactive live approvals remain
  **future** slices and are not claimed here. No adapter to LEO/OpenHawk is added
  in this ADR, and no external project becomes a runtime dependency.
- Guardrail: `scripts/check_project.py`, the repository-language rule and the
  full test suite must stay green; the harness ships with its own negative tests
  (unknown/oversized/dangerous commands refused; chained commands cannot launder
  a dangerous suffix; the snapshot never leaks a token or endpoint; the claim
  audit reports an unbacked success, an unexplained failure, an unknown state, an
  unsafe ledger row and an over-bound store, and repairs nothing).
