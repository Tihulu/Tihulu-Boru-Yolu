# Architecture and component ownership

## Objective

Offer a **locally installable, account-free (no external vendor sign-in required)** control plane on Pop!_OS and Ubuntu. Local application login for Langflow may still be required. External AI APIs require user-configured provider credentials.

## Topology

~~~mermaid
flowchart TB
  U[Owner / local UI] --> K[Kandev: tasks, roles, PR review]
  K --> A[Boru Adapter: job lifecycle and signed intent]
  U --> L[Langflow: versioned visual flows]
  L --> A
  A --> R[TIHULU-AUTO: router / scheduler / budget]
  R --> M[OpenCode: primary and subagent sessions]
  M --> J[Jan: local model API]
  R --> C[Cloud LLM providers, when allowed]
  R --> B[Trusted local policy / consent broker]
  B --> X[Local worker / isolated cloud-controlled sandbox]
  X --> B
  B --> P[Privacy Bridge: typed release gate]
  P --> R
  R --> A
  A --> K
~~~

The connecting **Boru Adapter**, trusted broker, sandbox provisioner and production Privacy Bridge are proposed components and require implementation. Diagram lines are *interfaces to build*, not proof of existing integration.

## Single source of truth

- **TIHULU-AUTO** owns task routing decisions, model selection, resource leases and retry state.
- **Kandev** owns Kanban status, user-visible task assignment, reviews and worktree lifecycle.
- **Langflow** owns flow definitions, transformations and visualization; it does not silently become a second router.
- **Trusted broker** owns enforceable authorization/consent, not model prompts or Langflow condition nodes.
- **Jan/OpenCode** stay as independent services; no modification to their model weights, databases or running sessions is assumed.

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
