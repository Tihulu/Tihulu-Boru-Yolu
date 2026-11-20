# Delivery roadmap — staged, rollback-first

**Policy freeze:** ADR-0004 preserves all owner-selected optimization modes, token budgets, privacy/minimal disclosure, LOCAL_ONLY/CLOUD_ALLOWED and four Shell profiles through the Boru Core independence transition. Neither optional TIHULU-AUTO nor OpenCode may be required for direct Jan inference. Changing a routing model cannot change any execution/disclosure grants.

Each milestone requires evidence and a reversible change. An incomplete milestone is **HOLD**, not 99% complete. Do not move production settings or merge changes just because a document exists.

## M0 — Repository and compatibility baseline (documentation)

**Scope:** English documentation, source-only config schema, CI checks, licensing decision, upstream version/license compatibility table.
**Exit:** doc links, example policy checks and synthetic tests pass; upstream version tags are recorded. **No production integration claimed.**
**Current:** drafted in this branch; real CI result pending.

## M1 — Safe independent local installs

**Scope:** pinned Kandev and Langflow in separate user-owned locations on Pop!_OS/Ubuntu, loopback-only, no autostart, explicit local login for Langflow, no interference with Jan/OpenCode.
**Exit:** health and bind checks, uninstall and restore dry run, synthetic Kanban/flow; other sessions unchanged.
**HOLD:** requires local host operator and approved installation.

## M2 — Independent Jan API and optional OpenCode adapter compatibility

**Scope:** direct Jan model inventory and one-small-model 3-turn chat test through Boru Core **without TIHULU-AUTO**, optional larger model sequential test; separately verify unmodified OpenCode standalone operation and real `subagent` invocation through a disposable profile (not `skill`). Langflow and Kandev linkage can follow as optional pilots.
**Exit:** child session evidence with actual provider and model; no Shell or private data.
**HOLD:** live provider tests required.

## M3 — Boru Adapter prototype

**Scope:** typed task envelopes, idempotency, Langflow API dispatcher, Kandev task event adapter (manual workflow fallback if needed), status mapping, test fixtures and cancellation.
**Exit:** a Kandev synthetic task triggers one authenticated Langflow flow and returns a verified child result, with no duplicate execution.
**HOLD:** upstream hook/API compatibility and adapter code not implemented.

## M4 — Routing modes and observability

**Scope:** independent **Boru Core** router (not TIHULU-AUTO), AUTO/ECONOMY/BALANCED/PERFORMANCE/MANUAL; separate LOCAL_ONLY/CLOUD_ALLOWED; actual token metrics or labelled estimates; bounded fallback without side effects.
**Exit:** deterministic simulation of provider quota failures and actual, approved provider test; model selection changes with mode while execution permissions do not.
**HOLD:** routing engine implementation and test evidence.

## M5 — Trusted local worker and Privacy Bridge

**Scope:** authenticated broker IPC, scoped operations, independent OS permission enforcement, approved result schemas, user consent UI, expiry/revoke/replay state and audit.
**Exit:** synthetic/adversarial unit tests and local integration tests demonstrate fail-closed behavior, no raw outputs, no unauthenticated Shell and no prompt-injected bypass.
**HOLD:** prototype is not production-verified.

## M6 — Optional cloud-driven Shell sandbox

**Scope:** user-toggleable CLOUD_SHELL_APPROVAL and CLOUD_SHELL_TRUSTED, disposable sandbox, explicitly mounted project scope, approval receipt, network policy, resource quotas, model provenance, cancellation and disclosure filters.
**Exit:** deny by default; verify no host escape or private data exposure; consent expiry/revocation; no silent escalation; reproducible rollback. Independent security review is mandatory.
**HOLD:** do not expose control path until M5 passes.

## M7 — Six-agent scheduling and resource lifecycle

**Scope:** DAG with dependency-aware dispatch, per-provider ceilings, local model memory leases, one large local model default, Jan-safe unload (owned idle only), cancellation and garbage collection.
**Exit:** at most six logical agents, no forced six heavy models; no OOM thrashing or unrelated session interruption; timeout and cancel release owned resources.
**HOLD:** actual Linux resource tests required.

## M8 — Production readiness and release

**Scope:** Ubuntu LTS and Pop!_OS test matrix; signed release artifacts or verifiable hashes, upgrade/rollback, config migration, system threat model, docs, audit privacy review, license, user-visible permissions.
**Exit:** reproducible install/uninstall on disposable VMs; no broken OpenCode/Jan; default no Shell cloud control; opt-in acceptance independently verified. **Public rollout requires explicit owner go/no-go.**

## Recommended issue breakdown

- P0: publish baseline architecture and trust decisions
- P0: test Kandev non-invasive local install
- P0: test Langflow localhost Jan text-only flow
- P0: prove independent Boru Core -> Jan text-only test with TIHULU-AUTO absent
- P0: validate optional OpenCode subagent adapter and child provider without TIHULU-AUTO
- P1: implement Boru Adapter task contract
- P1: implement router/budget/fallback and test mode separation
- P1: build policy broker with full consent test matrix
- P1: build OS-isolated execution boundary and disclosure gate
- P1: build explicitly approved cloud Shell sandbox profile
- P2: GPU/RAM/VRAM lease scheduler and process ownership
- P2: full Pop!_OS / Ubuntu acceptance & rollback
- P2: public release/security review

## Dependencies and parallelism

**No dependency on TIHULU-AUTO:** it may remain unfinished indefinitely without blocking any Boru Yolu milestone. The optional legacy adapter/import is a separately approved follow-up, not a release requirement. OpenCode and Jan are standalone third-party applications and must remain usable without Boru Yolu. Boru Core can invoke Jan directly before OpenCode, Langflow or Kandev integration exists.

M1 and M2 can progress independently in *separate* disposable environments. M3 may prototype text-only before M5, but cannot execute host commands. M4 can use simulated models before live integration. M6 **depends on M5**. M8 depends on all required security and platform gates.

All deliverables are maintained in English. Design changes require a new revision and dated ADR/update; preserve previous versions and test evidence in Git history.
