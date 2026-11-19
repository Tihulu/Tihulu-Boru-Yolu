# ADR-0004: Preserve user-selected optimization, privacy and execution policy

- Status: **Proposed — required compatibility contract**
- Date: 2026-11-20
- Related: ADR-0002 (execution profiles), ADR-0003 (Boru Core independence)

## Context

The owner requires the **original TIHULU-AUTO-era multi-model and subagent behavior** to remain present when Boru Yolu becomes a larger, independently developed platform. Independence from the unfinished TIHULU-AUTO project must not remove or silently relax token/cost optimization, high-performance scheduling, privacy controls, local-only Shell or explicitly consented cloud Shell.

## Decision: independently controlled policy axes

Keep these **orthogonal configuration and authorization domains**:

1. **Optimization mode:** `AUTO`, `ECONOMY` (token optimized), `BALANCED`, `PERFORMANCE`, `MANUAL`.
2. **Inference scope:** `LOCAL_ONLY`, `CLOUD_ALLOWED`. An enabled GitHub/Google/X account connector is not cloud-model inference consent.
3. **Shell execution profile:** `LOCAL_ISOLATED` (default), `HYBRID_PRIVATE`, `CLOUD_SHELL_APPROVAL`, `CLOUD_SHELL_TRUSTED`. Cloud-controlled commands must only execute inside an explicitly owner-approved broker-managed project sandbox, never unrestricted host Shell.
4. **Disclosure policy:** `MINIMUM_NECESSARY` (default), `SCOPED_APPROVED`. Disclosure authorization is independent of an inference request, GitHub write grant or Shell execution grant.

No performance mode, coordinator decision, provider fallback, connected-account sign-in, optional adapter failure, or credit exhaustion may change another axis or grant missing permissions.

## Optimization and performance

- AUTO: select tested compatible model(s) based on task complexity, quality, cost, latency, actual context/capabilities and privacy constraints.
- ECONOMY: lowest-cost suitable model and prompt/context minimization; prioritize tested local small models where appropriate. Do not sacrifice required quality or violate disclosure restrictions.
- BALANCED: weighted quality/latency/cost/resource profile.
- PERFORMANCE: strongest tested permitted models and bounded parallel agents, never automatic permission escalation or uncapped resource use.
- MANUAL: owner-selected model/provider; no silent override. If a selected model is down, ask or HOLD according to the authorized manual-mode policy.
- Cost/token accounting: observe actual provider usage if exposed; label estimates; respect hard quotas and request/cost/token budgets; compact context, avoid duplicate tasks and cap retries.
- Fallback: when 429, credit exhaustion, timeout or local memory pressure occurs, switch **only** among tested permitted providers while preserving recipient disclosure approvals, budget ceilings, Shell profile and local-only policy; otherwise HOLD.

## Shell and privacy contract

- **Default:** `LOCAL_ISOLATED` + `MINIMUM_NECESSARY`. Only a trusted independently authenticated local worker may execute approved host operations. Preferred operator can be authorized local Jan/Qwen, but its text does not itself authenticate the worker.
- `HYBRID_PRIVATE`: cloud may suggest typed requests or perform non-Shell reasoning, but local worker retains terminal control. Neither cloud nor a prompt can directly execute host Shell.
- `CLOUD_SHELL_APPROVAL`: separate live, operation-scoped owner consent, checked by a local authority, for broker-controlled project sandbox operations only.
- `CLOUD_SHELL_TRUSTED`: *explicitly owner-selected*, short-lived, revocable session grant with limited operation types, workspace scope, allowed models, call count, time, and resource/network budgets. Still sandbox only; no unrestricted host access.
- Owner approval to **run** an operation does **not** authorize disclosure of its raw stdout/stderr, file contents, machine environment, credentials, home directory, full listings, full tracebacks, or private repository contents.
- Privacy Bridge sends only minimum necessary typed data; prefer boolean/status/count/error-category. Escalate progressively: L0 status/boolean/count, L1 narrow non-sensitive field, L2 protected excerpt only with **separate recipient-bound, field-level, time-limited consent**.
- If the privacy gate is unavailable, uncertain or fails verification, **fail closed**: no private raw-output fallback and no silent cloud/tool escalation.
- Prevent leakage not only through model messages but GitHub issues/PRs, Kandev, Langflow, tracing, logs, artifacts, provider telemetry and retry paths.
- Offline local work continues without cloud providers or a connected GitHub/GitLab account; any approved remote repository network access is a separately controlled non-inference capability.

## Agents, resources and lifecycle

- Up to **six logical agents** in a dependency-aware graph; not six simultaneous large local models. Enforce per-provider/rate/VRAM/RAM/CPU quotas.
- A claimed subagent call must carry real child-session/provider/model/result evidence; neither loading a skill nor simulation counts.
- Cleanup only Boru-owned idle jobs/models. Never terminate existing external OpenCode/Jan work or modify their global configuration.
- Boru Core owns these controls independently of unfinished TIHULU-AUTO. TIHULU-AUTO may be attached later by an opt-in adapter but must not become a runtime dependency.

## Required non-regression tests

1. Across each routing mode, verify `execution.profile`, `privacy.policy`, `inference_scope` and account/repository permissions remain unchanged unless the owner explicitly changes that domain.
2. `LOCAL_ONLY` blocks all remote model inference and cloud fallback, even on cloud exhaustion or unsupported local model. `CLOUD_ALLOWED + LOCAL_ISOLATED` still forbids cloud host Shell.
3. No cloud Shell call without a valid, scoped consent grant and sandbox; revoked/expired grants deny.
4. No raw terminal or private source disclosure without separately authorized and narrowed output; missing Privacy Bridge yields HOLD.
5. Verify economy, performance, manual, quota exhaustion and provider fallback do not disclose extra information or increase Shell privileges.
6. Verify six-agent resource accounting, independent OpenCode/Jan, optional-adapter failure isolation, and rollback on Pop!_OS/Ubuntu.

## Change control

Changes to this permission/mode contract require a **new, dated ADR**, explicit owner review, an update to tests and documented opt-in migration. Never reinterpret or weaken defaults as a side effect of moving TIHULU-AUTO functionality into independent Boru Core.

**Status:** design constraints and sample-contract checks only. No production execution or Privacy Bridge isolation has been verified.
