# Codex end-to-end execution playbook — TIHULU Boru Yolu

> **Planning status:** READY FOR OWNER/CODEX REVIEW; **implementation status:** NOT STARTED / live acceptance HOLD. This document is a build specification and phased acceptance contract, not a statement that the described software exists.
>
> Primary repo: https://github.com/Tihulu/Tihulu-Boru-Yolu
> Current source-only baseline: draft PR #1 (`plan/architecture-security-profiles-ubuntu-popos`), linked tasks #2–#12. Exact branch, commit, and checks must be reverified when execution begins.
>
> Language for all repository content: **English**. Intended platforms: Pop!_OS 24.04 and supported Ubuntu LTS (first x86_64). Future ARM64 is contingent on verified runtime compatibility.

## A. Definition of the product

TIHULU Boru Yolu is an **independent, local-first, optional-cloud multi-agent development orchestration platform** with:

1. A **native Boru Core** scheduler, provider registry, task/result contracts, budget/routing engine, and actual subagent execution evidence. It has **no dependency on unfinished TIHULU-AUTO**.
2. Existing **Jan** as a directly usable independent local AI endpoint; existing **OpenCode** as an independent, optionally connected coding-agent application. Neither can be owned, modified, reconfigured, or terminated by Boru.
3. Optional **Kandev** task/agent UI and **Langflow** visual flows, linked through a versioned Boru Adapter after verifying real upstream interfaces (manual task handoff is acceptable until a supported hook exists).
4. AI connections: ChatGPT/OpenAI, Claude, Google Gemini/Vertex AI, GLM/Z.ai, Kimi/Moonshot, DeepSeek, NVIDIA, Grok/xAI and Jan/local. Use **only supported official** OAuth/account-login, cloud IAM, API-key, or native-client methods per provider. An account sign-in may yield **identity only**, not inference/subscription entitlement.
5. GitHub and GitLab repository management (issues, PR/MR, commits, reviews, CI statuses); GitHub Actions supported workflow-dispatch, observation, logs/artifacts, rerun/cancel and approved PR-based workflow edits. Self-hosted runners not required or implicitly configured.
6. The user-defined four **independent axes**: routing optimization, cloud inference policy, Shell execution profile and output disclosure. Rules are frozen in ADR-0002/0003/0004.
7. An independently enforcing trusted local execution/consent broker and **Privacy Bridge** (typed minimal disclosure, no unfiltered terminal output); **opt-in cloud-directed Shell only inside independently tested broker-controlled project sandboxes**, never native unrestricted host Shell.
8. Six **logical** agents max (configurable), capability-based assignment and DAG dependencies, model selection, prompt/token optimization, limited retry/fallback, budget tracking, provider and memory resource leases; never assume six heavy local models.
9. Local dashboard, EN/TR/DE localization, offline/local-only operation, installer/uninstaller/rollback, auditable work history and reproducible native Linux acceptance.

### Absolute non-regressions

- Boru Core runs when TIHULU-AUTO is absent. Jan local inference from Boru Core does **not** require OpenCode, Kandev or Langflow.
- OpenCode and Jan continue functioning when Boru is absent, stopped or removed.
- Routing modes: `AUTO`, `ECONOMY` (token optimized), `BALANCED`, `PERFORMANCE`, `MANUAL`.
- Inference: `LOCAL_ONLY` or `CLOUD_ALLOWED`.
- Execution: `LOCAL_ISOLATED` (default), `HYBRID_PRIVATE`, `CLOUD_SHELL_APPROVAL`, `CLOUD_SHELL_TRUSTED`.
- Disclosure: `MINIMUM_NECESSARY` (default), `SCOPED_APPROVED`.
- Switching optimization mode, model, provider, account, repository, quotas or running out of credits **cannot** expand execution, inference or data disclosure permission.
- Cloud models get only approved minimal typed output. L2 protected excerpts require destination-bound, field-scoped, expiring owner consent. Failed filtering/authorization means HOLD; **never send raw logs as fallback**.
- Account OAuth, GitHub Actions, CI status or GitHub write permissions must never implicitly authorize host Shell.
- Credentials are never committed, exposed to models, scraped from existing app token stores or emitted through GitHub/CI.

## B. Boot sequence for Codex — mandatory

**B0. Read-only audit, before creating or running anything:**

1. Inspect repository/default branch, PR #1, all existing issues #2–#12, workflow statuses, file tree, architecture, ADR-0002/0003/0004, security and privacy docs. Read root `AGENTS.md`.
2. Compare planned docs to actual source; identify which files are merely sketches, what code is missing, and whether PR #1 is draft/mergeable/green. Confirm no installed Boru runtime is presumed. Do **not** assume existing CI validates the security model.
3. Record current branch, SHA, observed test evidence and existing conflicts; do not print personal paths, local device inventories, secrets or full environment dumps.
4. Check actual availability, version, license and official APIs of Kandev, Langflow, OpenCode, Jan and providers. Pin verified versions in a compatibility table. Do not invent runtime compatibility or OAuth entitlements.
5. Create an issue-linked execution plan and first small implementation branch **from an appropriate reviewed baseline**. If PR #1 is still draft, prefer adding review fixes there or branch based on its verified commit rather than overwriting default `main`. Do not merge or rebase user branches without approval.
6. Read `harness/build-log.md`; update it with facts, proposed next work, blockers, evidence classes and tests. Distinguish DESIGN/STATIC PASS from LIVE PASS.
7. If host installation, provider login, production repository writes, privileged commands or external billing will be needed, list exact future approval gates at the start. Continue source-only implementation without waiting for approval that is not yet required.

### Engineering approach

- Prefer a **small, typed, local-first native core** and an independently testable broker. Candidate stack: Rust core/broker + SQLite and a lightweight web UI (TypeScript) with versioned JSON schemas. **First record an ADR** and check installed project constraints before committing to a stack. Do not force containers, Python runtime, CUDA, driver changes or services on existing systems.
- Optional adapters are separate modules and feature flags; a missing app/provider cannot block the offline core. Local end-user services bind loopback, no autostart at first.
- Use one functional vertical slice per PR with tests, negative cases, status and rollback. Split work among up to six development agents only if actual tooling supports isolated concurrency; do not manufacture child-agent proof.
- For secrets use OS keychain/keyring or an independently reviewed locked vault; configs/issue bodies/logs store opaque references only.
- Avoid separate competing authoritative model routers in Langflow/Kandev/OpenCode. **Boru Core** owns only Boru tasks and never takes ownership of standalone OpenCode workflows.

## C. Ordered implementation workstreams

### P0 — Correct and freeze the baseline
**Dependencies:** none. **Issues:** PR #1, #12 and ADRs.

Build: resolve contradictory documents, review source-only tests, document technology choice and licenses, create versioned interfaces, synthetic fixtures, CI and reproducible developer commands. Add explicit privilege and external-action review. Preserve prior design revisions via Git history.

**Gate:** draft baseline checks pass; docs do not claim runtime security; owner reviews architecture changes. Do not label host installs PASS.

### P1 — Independent Boru Core minimum executable
**Dependencies:** P0. **Issue:** #12.

Build: core CLI/service skeleton, versioned configuration, local state, `TaskEnvelope` and `AgentResult`, deterministic task states (CREATED/QUEUED/RUNNING/VERIFYING/REVIEW/DONE/HOLD/FAILED/CANCELLED), bounded task queue, model registry and health interface. Direct **Jan OpenAI-compatible, text-only** connector with tested 3-turn chat and true provider/model identity. Provide mock provider for CI while keeping mock vs real evidence explicit. No Shell and no cloud inference in first pilot.

**Gate:** Boru Core works with TIHULU-AUTO absent and without OpenCode/Kandev/Langflow; fake results can never be marked LIVE PASS. Existing Jan and OpenCode remain intact.

### P2 — Optional coding-agent and workflow adapters
**Dependencies:** P1. **Issues:** #2, #3, #4.

Build: optional OpenCode supported CLI/API adapter through disposable workspace, real child session IDs and model/provider evidence, separately verify bare OpenCode operation. Add Kandev and Langflow only in isolated pinned environments, with local authentication and loopback binding. Use documented task event hook / flow-run API where actually available; otherwise implement an explicit **manual** task-to-flow step. Typed results, cancellation, dedupe and adapters disabled by default.

**Gate:** real OpenCode subagent call, not a `skill` invocation; 3-turn Jan via Langflow; synthetic Kandev->Langflow workflow; clean stop does not affect existing apps.

### P3 — Model routing, token optimization and observability
**Dependencies:** P1; P2 not mandatory for direct model routing. **Issue:** #4.

Build: AUTO/ECONOMY/BALANCED/PERFORMANCE/MANUAL selection, model capabilities/verified context limits, actual vs estimated usage, token and cost ceilings, prompt/context reduction, retries with idempotency, provider cooldown, model fallbacks on 429/timeouts/credits/OOM, no duplicate side effects, per-provider and per-agent rate limits. In LOCAL_ONLY there are **zero remote model calls** under normal or fallback paths.

**Gate:** mode changes alter scheduling/quality/cost decisions but **never** alter Shell, inference or disclosure rights. Hard budget never exceeded intentionally; unknown credits marked UNKNOWN, not invented. Failure/timeout negative tests PASS.

### P4 — Real agent lifecycle and up-to-six logical agents
**Dependencies:** P1, P3. **Issue:** #7.

Build: DAG dependencies, subtask decomposition, verified child dispatch/results, resource leases (CPU/RAM/VRAM/rate), bounded concurrency, per-task cancellation and timeout cleanup, sequential local heavy-model loading default pending measurements, progress/lease evidence, orphan cleanup **only for Boru-owned resources**. Strict child identity proof.

**Gate:** six *logical* agents can cooperate under test, but only safe measured local physical concurrency; no unrelated Jan/OpenCode sessions killed and no false simulated delegation marked PASS.

### P5 — Trusted local broker and Privacy Bridge
**Dependencies:** P1; independent safety review before any live Shell. **Issue:** #5.

Build: authenticated local worker and session identities, separate broker authorization (not LLM-generated consent), operation allowlists, path scope confinement and race checks, authorization receipts, replay and expiry protection, deterministic typed result schemas, minimum necessary output, L0/L1/L2 recipient-bound disclosure, safe trace/log artifact handling, hard stop and local audit. Validate adversarial injection, symlink/path escapes, malformed nested fields, cancellation and failure states. No unrestricted local host Shell from cloud.

**Gate:** fail closed with missing broker/revoked grants/filter errors; no raw stdout or private files exposed; live local acceptance with negative tests **before** shipping any Shell tools.

### P6 — Optional cloud-directed Shell inside a sandbox
**Dependencies:** **P5 LIVE PASS, not source-only PASS.** **Issue:** #6.

Build: user-selectable `CLOUD_SHELL_APPROVAL` and `CLOUD_SHELL_TRUSTED`, disposable sandbox, constrained mounts/process/network, explicit provider/model/task/scope/max-call/expiry grants, revocation, proof of containment and output filtering. Default remains `LOCAL_ISOLATED`, with `HYBRID_PRIVATE` available for cloud reasoning but only local-worker Shell. No implicit root, host mounts, Docker socket or persistent remote listener.

**Gate:** denied/expired/replayed approval fails, sandbox escape/secret access tests are negative, revocation works, no raw disclosure, separate security review on Pop!_OS and Ubuntu. **Cannot be merged or enabled without explicit owner approval.**

### P7 — AI Provider Manager and approved login
**Dependencies:** P1 and P3 for text-only providers; P5 for sensitive connection flows. **Issues:** #10, #11.

Build: multi-account provider registry with capability/region/endpoint/billing/auth status; local encrypted or OS-protected token storage, connect/test/disconnect, consent, quotas and real model discovery. Target ChatGPT/OpenAI, Claude, Gemini and Vertex AI, GLM, Kimi, DeepSeek, NVIDIA, Grok/xAI, local Jan. Implement only documented legal OAuth/OIDC/PKCE/device/client-handoff flows for the *specific app category*; API-key/cloud IAM alternative where account sign-in is not permitted. Distinguish `SIGNED_IN_IDENTITY_ONLY` from `INFERENCE_AUTHORIZED` and `MODEL_TEST_PASSED`.

**Gate:** each supported provider responds to an actual explicitly permitted synthetic test request; revoke/expiry/failover verified. Never assume ChatGPT/Google consumer subscription automatically allows third-party API inference. No cookie scraping or unofficial auth. Unsupported sign-in paths are honestly marked UNSUPPORTED; optional providers do not block offline release.

### P8 — GitHub, GitLab and GitHub Actions
**Dependencies:** P1, P5 for trusted action authorization; can prototype read-only earlier. **Issues:** #8, #9.

Build: official API adapters, multi-account/repo separation, read/list/search issues, PR/MR, commits, comments, checks/pipelines, create branch, safe file changes on new branches, draft PR/MR, reviews and narrowly approved merge. GitHub Actions: discover workflow definitions; validate `workflow_dispatch` inputs; dispatch an **approved no-secrets disposable test workflow**; inspect exact run/job SHA, status, logs (redacted), artifacts, and supported rerun/cancel; fix failures through isolated PRs. Add multi-remote and mirroring as **explicit opt-in only**, and never silently copy private repositories to public locations.

**Gate:** real provider-backed object IDs and permission checks for every write. Read-only permission denies ALL write paths including indirect automation. Workflow privilege changes, publish/deploy and merges require separate owner approval; never treat green CI alone as production readiness.

### P9 — Kandev/Langflow unified workflows and dashboard
**Dependencies:** P2–P5; connector panels depend on P7/P8.

Build: accessible responsive local dashboard, task graph/agent status, routing/inference/Shell/disclosure selectors shown **separately**, connection tiles for AI and source control, model registry, budget and limits, privacy field-level approval dialog, start/stop/hard-stop, authorized resource status, provider fallback reasons, evidence links and EN/TR/DE localization. Langflow remains the visualization/flow component, Kandev task/PR board; neither is security authority.

**Gate:** UI cannot make a forbidden operation possible by toggling routing mode; all approvals backed by broker and tested expiry/revoke; accessibility and offline-friendly UI tests PASS.

### P10 — Security, quality, compatibility and release
**Dependencies:** all mandatory P0–P9 gates, optional mechanisms clearly declared. **Issues:** #7, #5, #6, #9 and #10 as applicable.

Build: reproducible user-space install/update/uninstall/rollback; pinned versions and checksums; migration backup dry run; no autostart by default; no Docker/CUDA dependency unless an optional profile. Test on **actual Pop!_OS 24.04 and Ubuntu LTS** clean disposable systems, with and without internet; conflicting ports, limited memory, provider 429, offline local use, bad OAuth callback, revoked GitHub scopes, CLI crash, cancellation, process teardown, permission prompts and rollback. Threat model, licensing, dependencies/SBOM and private-data audit. No unverified auto-release.

**Gate:** full acceptance matrix with recorded dates, OS, versions, exact commit, sanitized logs, tester and PASS/FAIL/HOLD; all **mandatory** gates PASS; explicit owner sign-off for public distribution, releases and deployments. If any safety-critical gate is HOLD, project is NOT DONE.

## D. Dependency graph

~~~mermaid
flowchart TD
  P0[Baseline review / ADRs] --> P1[Independent Boru Core]
  P1 --> P2[Jan/OpenCode/Kandev/Langflow adapters]
  P1 --> P3[Token optimization and routing]
  P3 --> P4[Six logical agents / resource leases]
  P1 --> P5[Trusted broker / Privacy Bridge]
  P5 --> P6[Opt-in sandbox Cloud Shell]
  P3 --> P7[AI provider connections / OAuth]
  P5 --> P7
  P5 --> P8[GitHub/GitLab/Actions write permissions]
  P2 --> P9[Unified dashboard / flows]
  P4 --> P9
  P7 --> P9
  P8 --> P9
  P6 --> P10[Security and platform acceptance]
  P9 --> P10
~~~

Early read-only provider, GitHub/GitLab, UI and Kandev/Langflow prototypes may be developed in isolated branches while P5 is in progress; no Shell or unauthorized writes. P6 is **strictly blocked by** live P5 acceptance. None of P0–P10 depends on TIHULU-AUTO.

## E. Test strategy and evidence

### Every implementation PR includes

- Linked issue and phase; scope, ADRs, changed files, compatible versions and explicit non-goals.
- Reproducible tests (unit, integration, negative, end-to-end or manual steps), exact version/commit, and whether evidence is MOCK / STATIC / LIVE.
- Security impact: inference recipient, Shell privileges, output fields, network access, credential scopes, protected branches and rollback.
- Failure/timeout/cancel/idempotency handling. No reruns of potentially completed side-effect operations without reconciliation.
- Unresolved gaps as HOLD with an exact blocker and safe next step.

### Required cross-cutting acceptance fixtures

1. Boru -> Jan direct 3-turn chat works without TIHULU-AUTO, OpenCode, Kandev, Langflow; no prompt-only claimed result.
2. OpenCode remains fully usable alone; optional Boru child session returns actual identity.
3. ECONOMY vs PERFORMANCE show measured routing differences without changes to any of the three authorization axes.
4. LOCAL_ONLY, provider fallback, API quota/429, timeout and context overflow never make remote inference.
5. LOCAL_ISOLATED plus cloud model: only trusted local Shell worker; cloud cannot run host Shell.
6. Cloud Shell without explicit grant, wrong model, wrong task/ref, expired/revoked grant, replay, or absent sandbox: denied.
7. Privacy Bridge failure, malicious output, extra keys, excessively nested payload, private path, raw log: denied without raw fallback.
8. User grants a single L2 excerpt to one recipient; second recipient or extra field remains denied.
9. Agent graph with 6 logical agents; no six-heavy-model assumption; cancellation releases only Boru-owned leases.
10. AI sign-in identity-only does not trigger inference; successful inference requires provider-authorized live response.
11. GitHub/GitLab read-only profile cannot create or modify anything; task cannot import workflow secrets as prompt text.
12. GitHub Actions dispatch observes verified workflow/run/job identifiers; invalid scope, recursive events and expired grant blocked.
13. Working basic offline core after disconnecting all cloud accounts; reversible install/uninstall; no changes to Jan/OpenCode.
14. Security tests and real isolated OS acceptance repeated on Pop!_OS and Ubuntu.

## F. Work allocation and limits

Use up to six **development roles** (not mandatory six running processes):

| Role | Focus | Constraints |
| --- | --- | --- |
| Architect/coordinator | Repo audit, ADRs, dependency graph, task/evidence ledger | Single authority for Boru work planning |
| Core engineer | Types, task state, persistence, Jan direct provider | No unintended external system changes |
| Adapter engineer | OpenCode/Kandev/Langflow, GitHub/GitLab | Real official API/child proof |
| AI and optimization | Provider catalog, OAuth, token/performance/fallback | No secret exposure; provider-specific terms |
| Security engineer | Broker, Privacy Bridge, sandbox and adversarial fixtures | Can block unsafe release; no false PASS |
| QA/release engineer | Linux matrix, CI, installer, rollback, documentation | Independent acceptance evidence |

Roles can run sequentially when credits or compute are limited. Avoid concurrent edits to identical files; each role works in separate branch/worktree with one coordinated merge queue.

## G. Evidence ledger and resumability

Maintain `harness/build-log.md` after each meaningful change or session. Required fields: time (UTC), current branch/SHA, phase/issue, what changed, actual test commands/results, current PASS/FAIL/HOLD, provider/session/run IDs only when safe, expected costs, risks, blockers, exact next actionable task. **Do not record private paths, token values, full terminal output or personal system inventory**.

Keep Git history as the historical record. Do not replace earlier decisions silently; update dated ADRs for architecture/security changes.

When the Codex session or credits end: commit safe changes to a branch, open/update draft PR if authorized, update the ledger, list unfinished steps and give a short exact restart instruction referencing the file and branch. **Never pretend to continue asynchronously.**

## H. Release completion and owner sign-off

`IMPLEMENTED` means code exists; `TESTED` means a reproducible observed test; `RELEASABLE` means all security, Linux, rollback and privacy gates passed and licensing was reviewed. No arbitrary overall percentage. Use milestone counts and explicit state instead.

Minimum user-visible `v1` acceptance:
- Boru Core independent and working with direct Jan, optional real OpenCode subagent, model routing/modes, up-to-six logical agent scheduler and recoverable task state.
- Secure local execution broker and minimum disclosure policy; owner-enabled cloud Shell sandbox only after independent security acceptance.
- Officially supported AI connection methods with honest inference eligibility; GitHub/GitLab connectors, approved GitHub Actions loop; usable dashboard with controls.
- Install, update, rollback, start/stop, backup/restore and clean uninstall independently verified on Pop!_OS/Ubuntu; offline local mode; no interference with Jan/OpenCode.
- No critical or high unresolved security findings; auditable scope and release evidence.
- **Owner explicitly approves final merge/release.** Until then keep DRAFT/HOLD, not completed.

## I. First Codex task (start here, before broader features)

> Review current PR #1, repo `AGENTS.md`, ADR-0003/0004 and this playbook. Verify the source-only baseline and identify missing core code. Create the first small independent Boru Core vertical-slice branch/PR implementing task types, a minimal CLI and mock provider plus tests, while planning (not claiming) the real Jan 3-turn pilot. Do not install or modify OpenCode/Jan or access private settings; don't enable Shell or cloud execution. Update `harness/build-log.md` and linked issue with exact evidence and follow-on tasks. Proceed to P1 only within existing approved repository scope; HOLD any host/account/security step requiring fresh consent.
