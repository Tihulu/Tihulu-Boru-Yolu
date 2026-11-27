# Further development — Jarvis × Boru Yolu

**Owner decision: 2026-11-27**
**Status: DEFERRED / NOT STARTED — planning only.**

This directory records future work, not an active milestone, implementation claim, or authorization to start coding. Do not automatically claim, schedule, implement, or count these items in the current standalone development progress. Start only after both projects have completed their current independent development and acceptance gates and the owner explicitly authorizes the next phase.

## 1. Scope and product boundaries

- [Boru Yolu](https://github.com/Tihulu/Tihulu-Boru-Yolu) and [Jarvis](https://github.com/Tihulu/Tihulu-Voice-Assistant) remain separate applications, repositories, releases and installation lifecycles.
- Jarvis remains a personal assistant; Boru Yolu remains an independent orchestration and task-execution application.
- Both must remain usable without the other installed, running or connected. Integration is optional, disabled by default and explicitly authorized.
- No monolithic merger, general TIHULU ecosystem, additional application integration, mandatory common installer, centralized infrastructure or separate bridge repository is planned. Do not introduce shared libraries or services unless a concrete need is demonstrated and separately approved.
- Different development models/agents may continue working on the two repositories; coordinate future changes using GitHub issues, explicit task ownership, pinned commits and reviewable PRs.

## 2. Entry gate (all required)

- [ ] Owner confirms completion of the current standalone Jarvis development scope.
- [ ] Owner confirms completion of the current standalone Boru Yolu development scope, including applicable P0–P10 gates in [#13](https://github.com/Tihulu/Tihulu-Boru-Yolu/issues/13).
- [ ] Record both accepted version tags/commit SHAs and reproducible regression baselines; report physical/live acceptance separately from automated tests.
- [ ] Verify standalone installation, operation, shutdown, recovery and rollback on supported platforms.
- [ ] Review existing adapter/bridge work, including [Boru #17](https://github.com/Tihulu/Tihulu-Boru-Yolu/issues/17) and [Jarvis #561](https://github.com/Tihulu/Tihulu-Voice-Assistant/issues/561), for overlap and reconcile any pending scope with the owner. Preserve accepted existing functionality and evidence.
- [ ] Obtain explicit owner go-ahead to activate this deferred plan.

Until all boxes are satisfied, this document is archival planning only. Do not pull forward new integration or migration work from this directory, change current release gates, or interrupt ongoing standalone development.

## 3. Rust-first where beneficial; Python where needed

Not a full rewrite and not a Rust-only mandate. Audit actual code and dependencies at activation; do not assume any component is currently implemented or written in a specific language.

Potential Rust candidates: task/pipeline state machine, scheduling and cancellation, agent/resource leases, model routing, permission broker, IPC/API, process supervision, persistence, checkpoint/recovery, CLI and native backend. Use Rust only when its measurable reliability, maintainability, resource consumption, deployment or concurrency benefits justify migration.

Keep Python for AI/ML dependencies, existing compatible workers, adapters and other components where it remains the best tool. Preserve working UI technology. Retain useful existing code and use its accepted behavior as a regression reference.

For each candidate:
1. Inventory dependencies, invariants, compatibility and current performance.
2. Record an ADR with keep/migrate decision and rationale; compare a small prototype against the accepted baseline.
3. Migrate one bounded component behind a versioned interface, preserving compatibility and rollback.
4. Verify behavior parity, error handling, authorization, performance, memory use and maintainability before changing defaults.
5. Stop or revert if migration offers no material benefit or regresses accepted behavior.

No artificial target for the percentage of Rust code. No forced replacement of stable Python solely for language consistency.

## 4. Optional bidirectional integration

Prefer a small versioned language-independent API/IPC contract in the existing repositories. Evaluate local authenticated IPC first; choose transport only after reviewing supported platforms and security requirements. No public listener or automatic trust.

- Capability discovery and version negotiation; distinguish available, authorized, tested and connected states.
- Jarvis can optionally delegate a complex task to Boru; Boru can request explicitly permitted Jarvis capabilities without gaining general access to the host.
- Typed task/event contracts: task ID, parent ID, actor and recipient, idempotency key, owner, scope, deadline, budget, status, cancellation, result and sanitized evidence.
- One scheduling authority per task; reject recursive delegation, enforce hop and concurrency limits, avoid duplicate side effects.
- Provide live progress, pending approval, cancellation, typed errors, timeouts, recovery and explicit disconnect controls.
- Preserve standalone behavior on absence, shutdown, version mismatch, disconnection or failure of the other application.
- Use bounded queues, resource limits and ownership-aware model/lease handling; neither application may terminate or modify the other's unrelated sessions.
- Keep external engines and harnesses optional; CLI-Anything is not mandatory.

## 5. Security and privacy

Each application retains its own independently enforced policy authority. Effective delegated permissions are the intersection of both policies and the owner's scoped grant. Fail closed on uncertainty; no privilege escalation, credential sharing or implicit access to local files, memory, shell or private output.

Preserve accepted local/cloud/hybrid modes and all existing policy axes; delegation must not weaken either product's restrictions. For Jarvis, cloud models never directly execute host shell; trusted local Jan/Qwen execution remains subject to existing approvals and minimum-necessary disclosure. Any already approved Boru sandbox mode remains confined to its own separately scoped policy and must never grant Jarvis or a remote model host-shell access. No new cloud-shell permission is introduced by this plan.

Authenticate local identities; require recipient-bound, revocable grants; validate schemas; protect secrets and raw output; audit redacted task traces. Test malformed input, prompt injection, replay, traversal, grant expiry/revocation, unauthorized access, cancellation, crashes, restart and resource exhaustion.

## 6. Future implementation order (only after entry gate)

| Phase | Deliverable |
|---|---|
| F0 | Re-audit both accepted releases, reconcile existing bridge work and agree scope |
| F1 | Evaluate Rust candidates and establish measured baseline; approve per-component migration decisions |
| F2 | Specify versioned task, capability, permission and event contracts; contract tests |
| F3 | Minimal isolated read-only discovery and synthetic task exchange |
| F4 | Optional bidirectional delegation, cancellation and progress with independent policy enforcement |
| F5 | Incremental justified Rust migrations, parity checks and rollback; may proceed independently after F1 |
| F6 | Resource contention, recovery, interoperability, standalone and adversarial integration tests |
| F7 | Independent review and owner acceptance; document opt-in integration, compatible versions and upgrade/rollback |

Each phase must produce reproducible evidence, small reviewable changes and an explicit PASS/FAIL/HOLD verdict. Do not merge unverified work into stable. Track future work separately from standalone project completion; use measured progress, remaining work and delta, not invented percentages.

## 7. Acceptance criteria

- Both apps operate independently when the other is absent or unavailable.
- Opt-in authenticated task delegation works in both directions with typed results and visible status.
- Duplicate execution, delegation loops, permission escalation and unauthorized disclosure are prevented by tested enforcement.
- Cancel/restart/version mismatch and incompatible or missing adapters produce bounded, safe failures.
- Each Rust migration shows behavioral parity and a documented tangible benefit, or is reverted.
- Existing stable features, configurations, provider credentials and user data remain intact.
- Separate automated results and real platform/hardware acceptance evidence; owner approval before enabling integrated use.

**Current implementation progress for this new deferred plan: not started. No implementation or runtime validation is claimed by this document.**
