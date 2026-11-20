# Boru Core — implemented slice (P1) and contracts

This document describes what the code in `boru/` **actually implements**.
Anything not listed here is not implemented; see
`docs/CODEX_EXECUTION_PLAYBOOK.md` for the remaining phases.

## Run it

~~~bash
python3 scripts/check_project.py
python3 -m unittest discover -s tests      # baseline + P1 suites
python3 -m boru demo                       # fixed offline synthetic task, no network
python3 -m boru --state-dir local-state demo   # durable task state in a directory you own
python3 -m boru --state-dir local-state status --task-id demo-1
python3 -m boru --state-dir local-state review --task-id demo-1 --accept
python3 -m boru providers                  # configured providers and models, no discovery call
python3 -m boru run --task task.json       # submit and dispatch one task
~~~

`local-state` must be an existing owner-only directory; Boru creates
`boru-state.sqlite` (mode 0600) and a lock file inside it. `--show-text` adds
the recorded reply text to local output only.

`examples/core.example.json` is a runnable offline configuration. The earlier
`examples/boru-yolu.example.json` remains a non-executable demonstration
document validated by the static checks.

## Contracts (versioned, `schema_version = 1`)

`TaskEnvelope` — `task_id`, `goal`, `complexity`, `capability_tags`,
`priority`, `parent_task_id`, `routing_mode`, `inference_scope`,
`execution_profile`, `disclosure_policy`, `allowed_agent_ids`, `max_parallel`,
`token_budget`, `cost_budget_usd`, `max_attempts`, `idempotency_key`,
`requester_identity`, `consent_reference`, `payload` (`messages` only),
optional `deadline`, `selected_provider`, `selected_model`.

`AgentResult` — `task_id`, `attempt_id`, `status`, `model_provider`,
`model_id`, `evidence_class` (`direct` / `user_reported` / `simulated` /
`unknown`), `typed_result`, `child_session_ref`, `evidence_refs`,
`duration_ms`, `usage_if_observed`, `redaction_policy_revision`,
`authorization_receipt_id`, `disclosure_level` (`L0` / `L1` / `L2`).

Unknown fields and private-carrying keys (`raw_stdout`, `environment`,
`api_key`, `home_path`, …) are rejected in both directions.

## Task states

`CREATED → CLASSIFIED → PLANNED → QUEUED → RUNNING → VERIFYING → REVIEW → DONE`,
with `FAILED` and `CANCELLED` terminal and `HOLD` resumable. Only an explicit
owner review promotes `REVIEW → DONE`.

## Implemented guarantees (verified by tests)

- Four policy axes are read-only inside the core; a mode change cannot widen
  them (`boru/policy.py`, `tests/test_policy.py`).
- A task whose axes differ from the approved policy is refused before dispatch.
- `LOCAL_ONLY` selects no remote provider; a task requesting remote inference
  under `LOCAL_ONLY` never reaches a provider.
- A token or cost budget that cannot be reserved before dispatch produces
  `HOLD/budget_unverifiable` with **zero** provider calls.
- An expired deadline produces `HOLD/deadline_exceeded` with zero calls.
- `MANUAL` routing requires an owner-selected provider and model.
- Only the `text` capability is accepted in this slice.
- The reply is re-checked against the dispatched provider, model and a
  non-empty request ID; a forged or mismatched reply becomes `FAILED`.
- `REVIEW` is never promoted without `review --accept`.
- Results are restricted to `max_result_fields` typed keys and never carry
  raw output fields.
- Interrupted `RUNNING`/`VERIFYING` tasks return to `HOLD` on restart; no
  dispatch is replayed automatically.
- Duplicate idempotency keys with different contents are refused; the same
  contents return the existing task.
- The state store refuses group/world-accessible state directories, symlinked
  paths, hard-linked state files, unknown schema versions and a second writer.

## Jan connector (direct, text-only)

`boru/providers/jan.py` posts to `{base_url}/chat/completions` with
`stream:false`, `tool_choice:"none"` and no tool definitions. It accepts only
a numeric loopback endpoint, an explicit owner-configured model allowlist and
`tool_execution_disabled=True`, because Jan's local server can proxy remote
providers and execute tools server-side. Redirects are not followed, no
environment proxy is consulted, request and response bytes are bounded and
usage is recorded only when the provider reports it.

This is a **transport**, not an authorization: it does not authenticate the
owner, grant Shell rights, or prove a security boundary.

## Not implemented in this slice (HOLD)

Weighted mode-dependent routing and fallback (P3), agent graphs and resource
leases (P4), the trusted broker and Privacy Bridge (P5), cloud-shell sandbox
(P6), provider OAuth/API connections (P7), GitHub/GitLab/Actions connectors
(P8), the dashboard (P9), and Linux install/rollback acceptance (P10).
