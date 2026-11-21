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

`discover_models()` and `health()` are behind an explicit
`allow_discovery` flag, because Jan's `/v1/models` may include remote
providers: discovery lists only IDs that are also in the operator allowlist,
and an absent allowlisted model is reported as `model_missing` rather than
silently substituted. `health()` returns only `{"status", "models_listed"}` —
never a model inventory.

This is a **transport**, not an authorization: it does not authenticate the
owner, grant Shell rights, or prove a security boundary.

## Routing (P3 slice)

`boru/router.py` ranks *permitted* candidates per optimization mode:

| Mode | Behaviour |
| --- | --- |
| `ECONOMY` | local first, then lowest declared cost tier; unknown cost is a penalty, never assumed zero |
| `BALANCED` | weighted quality/cost; unknown quality is a confidence penalty |
| `PERFORMANCE` | strongest declared quality tier within the hard limits |
| `AUTO` | complexity-driven: simple behaves like ECONOMY, medium BALANCED, difficult PERFORMANCE |
| `MANUAL` | exactly the owner-selected provider/model, never a substitution |

Fallback advances only to another already-permitted candidate, only for
`timeout` / `unavailable` / `rate_limited` / `server_error`, bounded by
`max_retries`, and it records health changes on the Boru-owned registry. A
terminal failure (`policy_denied`, `invalid_response`, `request_too_large`)
never retries. Under `LOCAL_ONLY` the candidate list contains **no remote
entry**, so no failure path can produce a remote call. `credits` and other
unobservable values stay `UNKNOWN`.

## Agent planning (P4 slice)

`boru/scheduler.py` holds up to **six logical agents** as scheduling roles,
never six concurrently loaded models. Plans declare `AgentSpec` entries with
`depends_on` dependencies and an optional `large_local_model` flag. The default
physical lease is **one** large local model until real RAM/VRAM measurements
exist; leases are counted, never guessed from a device inventory. `dispatch_ready`
runs only tasks whose dependencies are `DONE`, and `release` frees only
Boru-owned leases — nothing can stop, unload or reconfigure an external Jan or
OpenCode session.

## Privacy gate (P5 source slice, not a boundary)

`boru/privacy.py` is a deterministic, fail-closed release gate: it decides
which typed fields may leave for one named recipient and refuses everything
else (private-carrying field names, fields outside the level allowlist,
oversized or nested payloads, missing fields, oversized results). L2 needs an
explicit recipient-bound, field-scoped, expiring, nonce-protected owner grant;
without it the answer is denial, never a raw fallback.

`boru/broker.py` answers the adjacent question: may this named operation touch
this named resource for this task, right now?  It never executes anything.  An
operation must be on the owner's allowlist (`read_file_alias`, `list_dir_alias`,
`probe_path_alias`, `run_synthetic_command`), a resource must be a declared
**alias** — never a caller-supplied path, and escapes such as `..`, relative
paths and symlinked aliases are refused — and the request must carry a valid
worker attestation holding that resource scope plus a matching consent grant.
Replay, expiry, revocation, malformed requests and missing consent all deny;
an allowed decision becomes an `AuthorizationReceipt` carrying alias names and
typed outcomes only.

`boru/consent.py` persists those grants in an owner-only SQLite file
(`boru-consent.sqlite`, mode 0600, single writer) so a revoked or expired grant
stays denied after a restart, and it records every used nonce once. Grant
fields, recipients, tasks and levels are validated; no token, path or model
output is ever stored.

`boru/executor.py` adds the bounded local worker that performs the *acquisition
and reduction* steps for the three read-only operations: `probe_path_alias`
returns `exists`/`type`/`size`, `list_dir_alias` returns a bounded
`entry_count` (never names), and `read_file_alias` reports `exists`/`size`
without ever producing file content. Aliases are opened with
`O_DIRECTORY|O_NOFOLLOW`, receipts must be unexpired and carry an allowlisted
operation, and requesting any field the operation does not produce — including
`content`, `raw_stdout` or `file_contents` — is refused.

Still **not** implemented: an authenticated persistent worker identity store, a
live socket, OS confinement, any mutating or subprocess operation, and the
release of L2 excerpts to a model. Those remain HOLD pending an independent
security review.

## Cloud provider (P7 source slice, no live calls)

`boru/providers/cloud.py` is an OpenAI-compatible cloud transport with the same
bounded-exchange rules as the Jan transport, plus:

* HTTPS required unless the owner explicitly allows HTTP for a pinned host;
* an explicit model allowlist;
* credentials only as an **environment-variable name** in configuration, read
  at request time and never stored, logged or sent to another provider;
* an honest `connection_state`: `configured` (endpoint and models declared),
  `authenticated` (a credential is present), or `unavailable`.  An
  authenticated identity is **not** an inference entitlement: a
  `model_test_passed` state requires a real authorized call, which this
  repository does not make. `examples/cloud.example.json` demonstrates a
  configured-but-not-authenticated provider.

## 

`boru/dashboard.py` is a loopback-only status surface: `GET /` renders a
bounded HTML summary, `GET /status` returns JSON, `GET /task/<id>` shows one
task, and `POST /review` performs an **explicit, accepted-flag** owner review.
It performs no inference, changes no policy axis and exposes nothing beyond
`127.0.0.1` / `::1`. The root page localizes its fixed labels for English,
Turkish and German via `boru/i18n.py` (`?lang=en|tr|de`); unsupported
languages fall back to English. Only fixed labels are translated — task
content, provider output, paths and credentials never pass through the i18n
layer.

The optional **OpenCode adapter** (`boru/adapters/opencode.py`) is disabled by
default and speaks to a loopback OpenCode server through its official
`/api/session`, `/api/session/{id}/prompt` and `/interrupt` endpoints. It
requires a numeric loopback endpoint unless the owner explicitly allows a
remote host, truncates prompt text to a bounded limit, maps errors to safe
categories, and records the real session ID it received — a skill load or a
simulated reply is never counted as a subagent call.

`scripts/install_boru.sh` and `scripts/uninstall_boru.sh` are user-space
scripts for a chosen directory with a `--dry-run` mode, owner-only state
directory, launcher in a chosen `--bin-dir`, no sudo, no system service and no
autostart. `tests/test_install_scripts.py` runs a real install, runs
`python3 -m boru demo` from the installed copy, then uninstalls and verifies
only the Boru-owned paths were removed. This is a script round-trip on this
machine, **not** the Pop!_OS/Ubuntu clean-machine acceptance matrix.

## Repository connectors (P8 source slice, no live calls)

`boru/connectors/` implements the versioned contract from issue #8/#9:
capability roles `REPO_READ`, `ISSUE_WRITE`, `CODE_PR_WRITE`, `ACTIONS_DISPATCH`,
`ACTIONS_ADMIN`, `MERGE_RELEASE`; a `Grant` binding account, repository,
reference, operation set, call ceiling, expiry and disclosure recipient; and
`GitHubProvider`, an official REST connector whose every operation is checked
against a grant **before** any request. A denied operation raises
`ConnectorDenied` without leaving the host, records a sanitized audit event
and never includes a token, a response body or a private payload. `github.com`
API base URL is HTTPS-only unless the owner explicitly allows HTTP for a pinned
host, tokens only enter via an environment-variable name, and a token is
identity only — it authorizes nothing by itself.

`boru/auth/` implements the **official authorization-code + PKCE** flow:
`PkcePair` (S256), fresh `state` and `nonce`, a bounded numeric-loopback
redirect listener that captures exactly one authorization response and then
stops, state/nonce verification, and a token exchange that records an opaque
token **handle** in `TokenVault`. Token values are never stored in
configuration, prompts, logs, issues or CI artifacts; only handles, provider,
account, scopes and expiry are recorded, in an owner-only file. Endpoints must
be HTTPS and the redirect URI must be a numeric loopback address.

No provider is connected by this repository, and browser-only or
device-code modes stay `UNSUPPORTED` until a provider's official documentation
confirms them for this application category. Sign-in identity is not inference
entitlement: a `MODEL_TEST_PASSED` claim always requires a real authorized call.

`boru/connectors/gitlab.py` implements the same contract for GitLab.com and
owner-allowlisted self-managed instances against the official `/api/v4` API:
project paths are percent-encoded, `PRIVATE-TOKEN` is read only from an
environment-variable name, and the same grant boundary, call ceiling, expiry,
audit redaction and read-only isolation apply.

Tests prove a read-only profile creates no outbound request for any write
operation, the call ceiling and expiry are enforced, workflow endpoints are the
official ones, and HTTP 403/404/429/invalid JSON never leak a body.

## Local rejection ledger (audit slice)

`boru/audit.py` is the bounded, append-only local audit sink required by
`docs/OPERATIONS.md`: every denial (policy, contract, broker, disclosure,
connector, provider, budget, scheduler, executor, review, store, config) is
appended once, in an owner-only (0600) file inside the directory you name.
Entries hold only a category, a bounded subject identifier, a stable reason
code and a bounded detail kind — **no payload, no path, no token and no
provider text** — and there is no update or delete API, so an audit row cannot
be rewritten. Retention is bounded by a documented cap that prunes only the
oldest rows.

Terminal access: `python3 -m boru audit --audit-dir local-state/audit --limit 32`
prints bounded recent rejection rows as JSON (category, subject, reason, detail
kind, timestamp) — no payload, path, content or token. `--audit-dir` must name
an existing directory.

Provider capability/auth/billing matrix and the secret-free example are in
`docs/AI_PROVIDER_CONNECTIONS.md` (issue #10/#11 phase 1). It records that sign-in
identity is not inference authorization, that consumer Google-login inference and
third-party Claude subscription login are not offered, and that no provider
account is connected by this repository.

Clean-machine acceptance matrix and rollback checklist: `docs/OS_ACCEPTANCE.md`
(M01–M12 on Pop!_OS 24.04 and Ubuntu 24.04 LTS x86_64, all rows start as HOLD
until an owner runs them and records the outcome).

## Budgets, cooldowns and context bounds (P3 slice)

`boru/budgets.py` enforces ceilings honestly:

* a pre-dispatch reservation uses a **labelled deterministic estimate**
  (≈4 characters/token) plus the configured output ceiling; a task whose
  projection exceeds `token_budget` is held with
  `budget_exceeded_pre_dispatch` and **zero** provider calls;
* after the reply, actually *reported* usage is rechecked; exceeding the
  ceiling holds the task as `budget_exceeded_after_reported_usage` — no extra
  call, no permission widening, no silent fallback to an unmeasured path;
* a `cost_budget_usd` cannot be bounded before a call without a provider price
  table, so Boru refuses to start with `cost_ceiling_unresolvable_before_dispatch`
  instead of guessing a cost;
* `CooldownTracker` deprioritizes a candidate after `rate_limited`, `timeout`
  or `server_error`; if every candidate is cooling, the task is held rather
  than switching to a wider candidate;
* `compact()` deterministically bounds a conversation (system instruction plus
  the most recent turns) and reports how many turns were dropped. It is a
  heuristic bound, explicitly **not** semantic summarization.

Unknown usage stays unknown: only keys a provider actually reported are
recorded, and `usage_if_observed` stays empty otherwise.

## Live evidence so far (per acceptance entries)

- **A21 / Boru → Jan direct, three turns: LIVE PASS.** Three synthetic three-turn
  conversations ran through Boru Core against the owner's loopback Jan server
  (explicit endpoint, explicit allowlisted local model, tools disabled). Each
  recorded `provider=jan`, `model_id=<allowlisted id>`, `evidence_class=direct`
  and measured `usage_if_observed`; one was reviewed to `DONE`. A model outside
  the allowlist was refused with no provider call. Details are in
  `harness/build-log.md` (2026-11-20 18:30 UTC) and `docs/JAN_PILOT.md`.
- **A22 Jan standalone:** covered by the same run (Boru ran without
  TIHULU-AUTO, OpenCode, Kandev or Langflow).
- **A23 OpenCode child session: LIVE PASS (partially bound to Boru).** A real
  child session was created in a disposable, git-ignored directory through the
  owner's own local OpenCode server and answered a synthetic one-word prompt;
  the recording carries the session id, message id, agent `build`, model id and
  provider id. The pilot was driven with the official `opencode api` command
  (which authenticates itself) and both pilot sessions were deleted afterwards.
  `boru/adapters/opencode.py` is still source-tested only: driving it live needs
  the owner to authorize the auth material, so the adapter's live path is HOLD.

Plan and queue commands: `boru plan --file plan.json` submits a
dependency-aware plan of logical agents and dispatches every task whose
dependencies are `DONE`; dependent tasks stay untouched until you accept the
earlier result with `boru review --task-id <id> --accept`. `boru queue` lists the
tasks awaiting that explicit review. Re-running a plan resumes existing tasks
instead of failing.

Evidence report: `python3 scripts/evidence.py [--quick | --json]` runs the static
manifest check, the full unit suite, the offline demo and an install/run/
uninstall round trip in a temporary directory, then prints a sanitized block:
commit, Python version, platform, each check's status, `live_acceptance: HOLD`
and a MOCK/STATIC note. It records no private path, credential or device
inventory. `--quick` runs only the static check and the offline demo (unit suite and
install round trip reported as SKIPPED) so callers such as the test suite
cannot recurse into it. Exit status is 0 only when every mandatory check passes.

## Ledger wiring

`BoruCore` and `Broker` accept an optional `RejectionLedger` (an in-memory sink
by default, or a durable file when you pass one). Recorded denial paths today:
policy refusals on submit (`policy`), task holds and failures with their stable
reason codes (`scheduler`: `budget_exceeded_pre_dispatch`,
`budget_exceeded_after_reported_usage`, `deadline_exceeded`,
`provider_unavailable`, `missing_provider`, `cost_ceiling_unresolvable_before_dispatch`),
broker denials with the request's operation as the detail kind (`broker`),
disclosure refusals with the level as the detail kind (`disclosure`), and
GitHub/GitLab connector denials with the operation as the detail kind
(`connector`).
Nothing else is recorded, and no row contains a task goal, path, file content,
token or provider text.

Durable usage: `python -m boru --audit-dir local-state/audit ...` writes the
same ledger into `boru-audit.sqlite` inside the owner-only directory you name,
shared by the core, broker, disclosure gate and repository connectors.

The dashboard page is semantic and keyboard-only: `<html lang>` for the chosen
language, `aria-labelledby` sections, a `<caption>` on the status table, a
labelled review form with a submit button and no JavaScript (tests assert the
landmarks, heading order and labels).

Dashboard routes: `GET /` (bounded HTML status with a recent-rejections
section), `GET /status`, `GET /task/<id>`, `GET /queue` (tasks awaiting the
owner's explicit review), `GET /audit` (bounded recent ledger rows), and
`POST /review` which requires an explicit `accept: true`. The dashboard is
loopback-only, performs no inference and changes no policy axis.

## Cross-boundary tracer (issue #9)

`boru/boundary.py` refuses an outbound request that was never classified.
`CrossBoundaryGuard.declare()` records a classification per direction (task,
recipient, boundary, data class, grant reference); `check()` then allows a call
only when the request matches a declared direction, stays within the declared
data class and carries the declared grant reference. `BoruCore` consults the
guard before dispatching a Jan or cloud provider: an undeclared direction
becomes `HOLD/unclassified_boundary` with **no network call**, recorded in the
rejection ledger. In-process providers need no crossing.

## Worker identities (P5 slice)

`boru/workers.py` keeps owner-created worker identities with bounded
lifetimes: a worker id, its resource scopes, an expiry and a 256-bit secret
stored owner-only (0600) inside the directory you name. `valid()` verifies the
secret in constant time together with expiry and revocation, so a revoked or
expired identity never authorizes anything; there is no API that returns or
logs a secret, and at most eight workers exist at a time.

Still **not** implemented and requiring independent security review: host-level
authentication of the process presenting an identity, OS confinement, a
persistent live socket, and revocation of already-running work.

## End-to-end local pipeline (P5 slice)

`boru/pipeline.py` runs the local half of the Privacy Bridge in one call:
broker authorization (worker identity + consent grant), executor acquisition
(typed fields only, alias-confined, read-only), disclosure decision, and a
ledger row per step. Denials fail closed: a missing/expired/wrong-operation
grant, a revoked worker, L2 under `MINIMUM_NECESSARY`, and any field the
operation does not produce all deny before any data is released. A success
returns typed fields only — a directory listing returns a count, a file read
returns metadata, and raw content never appears.

The remote half (real recipient, L2 excerpt release, OS isolation) remains HOLD
pending independent security review.

## Cloud-Shell grant contract (P6 decisions only)

`boru/sandbox.py` implements the authorization half of
`docs/SECURITY_MODES.md`: `SandboxGrant` binds grant id, owner, recipient
provider **and model**, task, sandbox id, allowlisted operation types,
resource aliases, field disclosures, expiry, call ceiling and nonce;
`SandboxBroker` denies on an invalid, revoked, expired, operation-not-granted,
resource-not-granted, field-not-granted, wrong-worker-scope, replayed-nonce,
exhausted or missing-sandbox request, and records each denial in the ledger.

Only the four alias-confined read-only sandbox operations exist; host-level
Shell is deliberately absent. A decision here authorizes nothing: no process,
container, mount or network is created, so P6 stays **blocked** until the P5
broker passes live acceptance and the owner explicitly consents.

## Not implemented in this slice (HOLD)

The trusted broker, authenticated worker and OS isolation; dashboard
localization/accessibility review; remote provider OAuth; the full OS
acceptance matrix (A01–A19), repository license choice and release approval.
(P5), cloud-shell sandbox (P6), provider OAuth/API connections (P7),
GitHub/GitLab/Actions connectors (P8), the dashboard (P9), and Linux
install/rollback acceptance (P10).
