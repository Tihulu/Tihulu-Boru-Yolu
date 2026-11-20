# Architecture and component ownership

## Objective

Offer a **locally installable, account-free (no external vendor sign-in required)** control plane on Pop!_OS and Ubuntu. Local application login for Langflow may still be required. External AI APIs require user-configured provider credentials.

## Topology

~~~mermaid
flowchart TB
  U[Owner / local UI] --> K[Kandev: tasks, roles, PR review]
  U --> L[Langflow: visual flows]
  K --> A[Boru Adapter: typed tasks]
  L --> A
  A --> R[Boru Core: own router / scheduler / budgets]
  R --> O[OpenCode: optional standalone coding-agent adapter]
  R --> J[Jan: direct local model API]
  R --> C[Authorized cloud AI providers]
  R -. optional legacy bridge, never required .-> T[TIHULU-AUTO]
  O -. independently configured Jan integration .-> J
  R --> B[Trusted local authorization broker]
  B --> X[Local worker or isolated cloud-controlled sandbox]
  X --> B
  B --> P[Privacy Bridge: typed release gate]
  P --> R
  R --> A
  A --> K
~~~

This is a **proposed** integration topology, not live deployment evidence. **Boru Core is implemented independently** of TIHULU-AUTO. Both OpenCode and Jan remain standalone external applications; either can run normally with Boru Yolu, Kandev, Langflow or TIHULU-AUTO shut down. Jan can be accessed directly from Boru Core without going through OpenCode. OpenCode may have its own Jan connection without Boru Core.

## Ownership and dependency rules

- **Boru Core (native)** is the *only routing authority for Boru Yolu tasks*: scheduling, model selection, resource leases, retry state, budget accounting and real child-session evidence. This is a new implementation, **not a wrapper that requires TIHULU-AUTO to work**.
- **TIHULU-AUTO** is a *separate unfinished project* and optional legacy adapter/import source only. It is disabled by default. It may be connected later through versioned interfaces, with explicit user approval and no automatic migration; it cannot be a dependency of M1–M8.
- **OpenCode** remains an independently installed and usable coding application. Boru uses an optional supported OpenCode API/CLI adapter. Boru does not rewrite its global agent/provider settings, own its running sessions, or require any TIHULU-AUTO agent.
- **Jan** remains an independent local model server. Boru can call its supported API directly without OpenCode, TIHULU-AUTO, Kandev or Langflow.
- **Kandev** owns task board, user-facing assignments, reviews and worktrees; **Langflow** owns visual flow definitions. Both are optional control surfaces, not the engine for local model calls.
- **Trusted broker** independently enforces consent, Shell restrictions and disclosure policies rather than trusting AI prompts or visual flow nodes.
- Any optional component may be unavailable: record HOLD for only the affected integration while preserving Boru Core's independent provider/agent capabilities.

## Standalone acceptance

1. OpenCode starts and executes its existing independent workflows with Boru Yolu and TIHULU-AUTO absent.
2. Jan serves its existing supported local model API with Boru Yolu and TIHULU-AUTO absent.
3. Boru Core starts in its limited text-only test mode and invokes a directly configured Jan model with TIHULU-AUTO absent and no OpenCode subagent.
4. An optional supported OpenCode child-session adapter provides real provider/model/session evidence without relying on TIHULU-AUTO-specific agents.
5. Disabling an unavailable optional adapter never triggers credential exports, silent configuration writes or broader execution rights.

## Layers

1. UI: Kandev board, Langflow flow editor, optional Boru status dashboard.
2. Control plane: adapter, routing service, scheduler, health, budgets and cancellation.
3. Data plane: OpenCode agents, Jan local API, authorized cloud inference endpoints.
4. Security plane: trusted execution broker, OS sandbox, separate disclosure gate, independent audit store.
5. Operations: service lifecycle, rollback, backups, health probes, active-session protection.

## Task lifecycle

`CREATED -> CLASSIFIED -> PLANNED -> AWAITING_APPROVAL? -> QUEUED -> RUNNING -> VERIFYING -> REVIEW -> DONE`

`FAILED`, `BLOCKED`, `CANCELLED` and `HOLD` are separate terminal/paused states. An agent's self-report cannot turn an unverified test into `DONE`. Each stage stores evidence type (`direct`, `user-reported`, `simulated` or `unknown`) with timestamps and model IDs.

Each job carries a stable `task_id`, immutable attempt IDs, parent/child IDs, idempotency keys and an output disclosure classification. Avoid storing sensitive prompts inside public GitHub issues or Kandev descriptions.

## Proposed typed contracts

`TaskEnvelope`:
- `task_id`, `parent_task_id` (optional), `workflow_revision`, `goal` (redacted/approved representation)
- `complexity` = simple / medium / difficult, `capability_tags`, `priority`, `deadline` (optional)
- `routing_mode` and `inference_scope`, independent `execution_profile`, `disclosure_policy`
- `allowed_agent_ids`, `max_parallel`, `token_budget`, `cost_budget`
- `requester_identity` and opaque `consent_reference` (never a user-set boolean)

`AgentResult`:
- `attempt_id`, `model_provider`, `model_id`, `child_session_ref`
- `status`, `typed_result`, `evidence_refs`, `duration_ms`, `usage_if_observed`
- `redaction_policy_revision` and `authorization_receipt_id` where applicable

## Adapter strategy

Phase 1: standalone Kandev and Langflow, no automatic writes.
Phase 2: Langflow reads approved model catalog, calls Jan text-only and returns synthetic results.
Phase 3: adapter maps **documented and tested** Kandev workflow/task events to Langflow API run calls, never by scraping UI. If Kandev lacks a supported hook for a use case, keep a manual transition and mark automated hookup HOLD.
Phase 4: route tool requests through broker with independent enforcement; without it, text-only mode remains functional.

**No direct Langflow custom Python component or Kandev shell step may bypass broker decisions.** Native tools must be disabled/isolated in restricted profiles; audit launch-time permissions and actual process capabilities.

## Distribution

Support Ubuntu LTS and Pop!_OS based on supported Ubuntu packages, x86_64 first. Keep package pinning, installation directories, environment files and service boundaries separate. Add ARM64 when upstream runtime and integration tests are verified.

No privileged system daemon, container engine, CUDA toolkit, driver change, third-party cloud login or background listener is required to read this repository.
