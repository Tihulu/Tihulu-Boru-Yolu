# TIHULU Boru Yolu — Evidence-Based Build Log

> This log is the single operational handoff ledger for Codex. **Do not record private paths, credentials, raw terminal logs, device inventories or personal system data.** Git commits and dated entries preserve history.

## Current snapshot — 2026-11-20 (UTC)

- **Repository:** `Tihulu/Tihulu-Boru-Yolu`
- **Current planning branch:** `plan/architecture-security-profiles-ubuntu-popos`
- **Current planning PR:** #1 — draft, not merged.
- **Master delivery coordination:** issue #13 (Codex P0–P10); workstream issues #2–#12 remain linked.
- **Current work:** documented project/architecture, ADR-0001 to ADR-0004, static contracts and test scaffold, Codex execution playbook.
- **Runtime state:** Boru Core, trusted broker, Privacy Bridge, Kandev/Langflow, provider OAuth, GitHub/GitLab app adapter, agent scheduler and installer are **NOT IMPLEMENTED / LIVE ACCEPTANCE HOLD** in this repository. Do not infer working software from documentation.
- **Existing Jan/OpenCode:** external user applications; independent, untouched by these repository-planning commits. No host-level verification conducted in this session.
- **Historical evidence:** draft PR #1 previously had successful `Source-only contract checks` workflow runs (most recently observed run #13 before playbook files were added). Treat any later commit as **NOT VERIFIED** until its own CI run is checked.
- **Code changes during this planning update:** only English repository documentation/instructions and this ledger; no app installation, model invocation, cloud OAuth login or Shell sandbox implemented.
- **Technical authority:** `AGENTS.md`, `docs/CODEX_EXECUTION_PLAYBOOK.md`, ADR-0003 (native Boru Core independence), ADR-0004 (original mode/privacy guarantees), ADR-0002 (Shell profiles).

## Workstream status

| Phase | Description | Current | Evidence / blocker |
| --- | --- | --- | --- |
| P0 | Baseline, docs, ADRs, source contracts | DESIGNED / review required | Draft PR #1; CI must be rechecked |
| P1 | Independent Boru Core + direct Jan | HOLD | No runtime implementation / live Jan test |
| P2 | OpenCode/Kandev/Langflow adapters | HOLD | No live integration evidence |
| P3 | Token/performance routing and fallback | HOLD | Contracts documented; engine missing |
| P4 | Six logical agents and resource leases | HOLD | Scheduler missing |
| P5 | Trusted local broker / Privacy Bridge | HOLD | Design only; independent security tests missing |
| P6 | Opt-in cloud Shell sandbox | HOLD | Blocked by P5 live acceptance and owner consent |
| P7 | AI provider registry + OAuth/API | HOLD | Design/issues only; no connected accounts |
| P8 | GitHub/GitLab/Actions in-app connectors | HOLD | Planning tasks only; app implementation missing |
| P9 | Unified dashboard / workflows / localization | HOLD | No app implementation |
| P10 | Native Linux release/security/rollback | HOLD | No clean machine acceptance or release approval |

## First executable next action

1. Re-read `AGENTS.md`, `docs/CODEX_EXECUTION_PLAYBOOK.md`, current PR #1, ADRs 0002/0003/0004 and related issues.
2. Inspect actual repository worktree and CI status at the current HEAD; verify these documents have no stale claims or broken references.
3. Create a **separate, small P1 implementation PR** from the owner-approved reviewed baseline, starting with native Boru Core task/result types, CLI scaffold, mock test provider and idempotent state transitions; write tests.
4. Document a real Jan direct, text-only 3-turn test plan. Do not claim it passed without an approved host-side run.
5. Leave Jan, OpenCode and TIHULU-AUTO settings/session data untouched. Do not request OAuth credentials, external billing or host Shell for source-only work.
6. Update this ledger with the new commit SHA, exact tests and next action.

## Session entry template

### YYYY-MM-DD HH:MM UTC — <short description>

- **Branch / commit:**
- **Issue / PR / phase:**
- **Changes made:**
- **Tests:** `command` -> PASS / FAIL / HOLD, environment and type (MOCK / STATIC / LIVE)
- **Security / privacy implications:**
- **Approval required (if any):**
- **Blocked tasks and reason:**
- **Next action (one precise step):**

Never mark an entire phase PASS because one unit test passed. Do not overwrite past entries.

---

### 2026-11-20 05:40 UTC — P1 Boru Core offline slice implemented (branch p1/boru-core-vertical-slice)

- **Branch / commit:** `p1/boru-core-vertical-slice` (from `f90fd3ed2e5e19d07e22fc4d60241c9c5c04ddc5`)
- **Issue / PR / phase:** issue #12 and master #13 — P1 (Boru Core minimum executable slice)
- **Baseline audit (P0 facts):** draft PR #1 still open, draft, not merged, head `f90fd3ed2e5e19d07e22fc4d60241c9c5c04ddc5`, base `main` `5056194012f27d511aa7a2029fafd896590214d2`; CI run **Source-only contract checks** on that head = **success** (run 21). Remote `main` HEAD `5056194…`, branch `plan/architecture-security-profiles-ubuntu-popos` ahead of main. CI runner `ubuntu-24.04` / Python 3.12, workflows: `scripts/check_project.py` + `unittest discover -s tests`.
- **Changes made:** new `boru/` package — `errors.py`, `policy.py` (four orthogonal axes, safe LOCAL_ONLY default), `types.py` (`TaskEnvelope`/`AgentResult` typed contracts), `state.py` (deterministic states), `queue.py` (bounded, replay-protected), `registry.py` (explicit locality), `store.py` (SQLite task state, 0600, single writer), `config.py` (versioned config), `core.py` (dispatch/verify/review), `cli.py`, `__main__.py`; `boru/providers/{base,mock,jan}.py`; tests `test_policy`, `test_typed_contracts`, `test_state`, `test_queue`, `test_registry`, `test_store`, `test_providers`, `test_core`, `test_cli`; docs `docs/ADRS/0005-boru-core-runtime-slice.md`, `docs/BORU_CORE.md`, `docs/JAN_PILOT.md`; runnable `examples/core.example.json`; `scripts/check_project.py` extended to require the P1 manifest.
- **Tests (source-only, Linux):** `python3 scripts/check_project.py` → **PASS** (static); `python3 -m unittest discover -s tests` → **PASS, 142 tests** (baseline 21 + 121 new); `python3 -m boru demo` → `REVIEW`, `evidence_class=simulated`, `live_acceptance=HOLD`. Python 3.13.9, git 2.43.0. Evidence class: **MOCK / STATIC only**.
- **Security / privacy implications:** no Shell tool, no cloud inference, no network endpoints, no credentials, no autostart. Defaults `LOCAL_ONLY` + `LOCAL_ISOLATED` + `MINIMUM_NECESSARY`. Reply text only appears in output with an explicit local `--show-text`. State confined to an owner-created, owner-only directory. Simulated evidence can never be promoted to `DONE` without an explicit owner review, and never becomes `direct`.
- **Approval required:** live Jan 3-turn pilot (endpoint, local model ID, tools disabled) — owner approval; adapters/install/OAuth/cloud/merge/release remain HOLD.
- **Blocked tasks and reason:** live Jan acceptance (A21/A22) HOLD pending approved pilot; P3 weighted routing HOLD by design (not simulated); P2/P4–P10 unchanged.
- **Next action (one precise step):** push the branch, open a draft PR against `plan/architecture-security-profiles-ubuntu-popos`, then post this evidence to issues #12 and #13.

- **CI (static):** run 22 on `7394c5b` (branch `p1/boru-core-vertical-slice`) → `Source-only contract checks` **success** (https://github.com/Tihulu/Tihulu-Boru-Yolu/actions/runs/44696839568). Static only: no runtime/security proof.
- **Draft PR:** https://github.com/Tihulu/Tihulu-Boru-Yolu/pull/14 — draft, base `plan/architecture-security-profiles-ubuntu-popos`, head `p1/boru-core-vertical-slice`. `main` untouched, PR #1 untouched, no merge.
- **Issue comments:** #12 and #13 updated with the same evidence set.
- **Phase status:** P0 STATIC PASS; P1 STATIC PASS (MOCK); P2–P10 HOLD.

- **Live Jan pilot attempt (2026-11-20, UTC):** `GET http://127.0.0.1:1337/v1/models` returned no body (HTTP 000, connection refused) and port 1337 was not listening; Jan's local API server is not running in this session. **Live acceptance remains HOLD**; no simulated result was substituted. Next action: rerun `docs/JAN_PILOT.md` with Jan's server started and an owner-confirmed endpoint, local model ID and tools-disabled setting.

---

### 2026-11-20 07:30 UTC — P3 routing slice added (commit to `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/router.py` (mode-aware ranking, permitted-only candidates, bounded fallback); `boru/registry.py` extended with declared `cost_tier` / `quality_tier` and construction-time validation; `boru/core.py` now dispatches through the router with a bounded retry chain and never widens the four policy axes; new `tests/test_router.py` and `tests/test_core.py::FallbackIntegrationTests`.
- **Tests observed:** `python3 scripts/check_project.py` → PASS; `python3 -m unittest discover -s tests` → PASS, **161 tests**; `python3 -m boru demo --show-text` → `REVIEW` / `simulated` / `live_acceptance=HOLD`. Evidence class: MOCK / STATIC only.
- **Security implications:** fallback can select only an already-permitted candidate; `LOCAL_ONLY` holds no remote candidate on any path; terminal failures are not retried; unobservable credits are recorded as `UNKNOWN`.
- **Live Jan pilot:** still HOLD — Jan's local API server was not listening on the configured loopback port during this session, so no live inference was recorded.

---

### 2026-11-20 07:50 UTC — P4 logical-agent planner added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/scheduler.py` (`AgentSpec`, `AgentScheduler`, `LeaseLedger`, `build_envelopes`); `BoruCore.submit_plan` / `plan_states` / `dispatch_ready` / `dispatch` with DAG-aware dispatch and lease-gated starts; `tests/test_scheduler.py` (unit + plan integration).
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **178 tests**; `python -m boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. MOCK/STATIC only.
- **Security implications:** six *logical* agents max, one large local model lease by default, leases counted rather than inferred from host inventories, and cleanup limited to Boru-owned leases.
- **Blocked:** live Jan pilot (Jan local API server not listening), optional adapters, broker/Privacy Bridge (P5), cloud Shell (P6), providers (P7), connectors (P8), dashboard (P9), install/rollback (P10).

---

### 2026-11-20 08:10 UTC — P5 disclosure gate added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/privacy.py` (`DisclosureGate`, `DisclosureRequest`, `ConsentStore`, L0/L1/L2 field allowlists, replay-protected grants) and `tests/test_privacy.py` (unit + adversarial: replay, wrong recipient/task/field, expiry, revocation, missing store, raw refusal, payload shape).
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **197 tests**; `python -m boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. MOCK/STATIC only.
- **Security implications:** this is a deterministic release gate, explicitly **not** a broker or a security boundary; fail-closed by construction; private field names refused at every level; L2 requires a scoped grant or is denied. Live broker, authenticated worker, OS isolation, persistent consent store and independent security review remain HOLD.

---

### 2026-11-20 08:20 UTC — Handoff state (Codex resume)

- **Branch:** `p1/boru-core-vertical-slice`, head `1342091` (draft PR #14 against `plan/architecture-security-profiles-ubuntu-popos`).
- **Verified locally at this commit:** `scripts/check_project.py` PASS; `python3 -m unittest discover -s tests` PASS **197 tests**; `python3 -m boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. All evidence MOCK/STATIC.
- **CI:** run 25 on `864747f` success. Run 26 on `1342091` was still in progress when this entry was written; **verify it before claiming CI PASS for the final commit**.
- **Implemented and unit-tested:** P1 core slice (contracts, states, store, CLI, providers), P3 mode-aware routing with bounded policy-safe fallback, P4 logical-agent planner with counted leases, P5 fail-closed typed disclosure gate (gate only, not a broker).
- **Still HOLD with exact next action:**
  1. Live Jan 3-turn pilot: start Jan's local API server, then run `docs/JAN_PILOT.md` with an owner-confirmed loopback endpoint, exact local model ID and server-side tool execution disabled; record provider/model/request IDs.
  2. P5 broker hardening: authenticated worker identity, OS confinement, persistent consent store and revocation; independent security review before any live disclosure path.
  3. P6 cloud Shell sandbox: blocked until P5 live acceptance; requires explicit owner consent and a disposable sandbox.
  4. P7 provider OAuth/API connections; P8 GitHub/GitLab/Actions connectors; P9 dashboard; P10 Pop!_OS/Ubuntu install and rollback acceptance; repository license choice; owner release approval.
- **Restart instruction:** check out `p1/boru-core-vertical-slice`, read this ledger entry and `docs/BORU_CORE.md`, run the two commands above, then continue with item 1 or the next source-only slice. Do not re-write the existing `boru/` modules; extend them.

---

### 2026-11-20 08:40 UTC — P7 cloud provider transport added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/providers/cloud.py` (HTTPS-enforced OpenAI-compatible cloud transport, explicit model allowlist, `api_key_env` credential indirection, honest `connection_state`), `boru/config.py` + `boru/core.py` + CLI wiring, `examples/cloud.example.json`, `tests/test_cloud_provider.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **211 tests**; `python3 -m boru --config examples/cloud.example.json providers --show-text` reports `configured` without a credential and `authenticated` with one, with `identity_is_not_inference: true`. MOCK/STATIC only.
- **Security implications:** no credential value is stored, logged or forwarded; identity never implies inference or disclosure rights; `LOCAL_ONLY` still refuses cloud candidates through the router. No live provider call was made and no provider entitlement is claimed.
- **Blocked:** live Jan pilot (Jan API server not running), OAuth flows and provider accounts (P7 remaining), P8/P9/P10.

---

### 2026-11-20 09:00 UTC — P9 dashboard and P10 installer slices added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/dashboard.py` (loopback status surface + explicit review action), `scripts/install_boru.sh` / `scripts/uninstall_boru.sh` (user-space, dry-run, no service/autostart, removes only Boru-owned paths), `tests/test_dashboard.py`, `tests/test_install_scripts.py`, docs/ACCEPTance + INSTALL updates.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **225 tests**; `scripts/install_boru.sh --dry-run` and `uninstall_boru.sh --dry-run` exit 0 creating nothing; a real install → `boru demo` (REVIEW, simulated, live_acceptance HOLD) → uninstall round trip passed on a temporary directory. MOCK/STATIC only.
- **Security implications:** dashboard binds loopback only, runs no inference, and requires an explicit `accept: true` for review; the installer asks for no privileges and cannot remove Jan/OpenCode/TIHULU-AUTO data.
- **Still HOLD:** Pop!_OS/Ubuntu clean-machine acceptance matrix, localization/accessibility review, broker hardening, OAuth, cloud Shell, release.

---

### 2026-11-20 09:10 UTC — Final handoff for this round (commit `97cb088`)

- **Branch / draft PR:** `p1/boru-core-vertical-slice`, draft PR #14 against `plan/architecture-security-profiles-ubuntu-popos` (base of still-open draft PR #1). `main` and PR #1 untouched, nothing merged.
- **Commits:** `7394c5b` (P1 core) → `45f0ceb` (P3 routing) → `864747f` (P4 planner) → `1342091` (P5 gate) → `e6bb965` (handoff ledger) → `5f79311` (P7 cloud) → `97cb088` (P9 dashboard + P10 installer).
- **Verified:** `scripts/check_project.py` PASS; `python3 -m unittest discover -s tests` PASS **225 tests**; `boru demo` → `REVIEW` / `simulated` / `live_acceptance=HOLD`; installer round trip on a temp dir. CI runs 27/28/29 all **success**. Evidence class: MOCK / STATIC only.
- **Remaining HOLD with exact next actions:**
  1. Live Jan 3-turn pilot: start Jan's local API server (it was **not running** in either session), then run `docs/JAN_PILOT.md` with an owner-confirmed loopback endpoint, exact local model ID and server-side tool execution disabled; record provider/model/request IDs.
  2. P5 broker hardening and independent security review: authenticated worker identity, OS confinement, persistent consent store and revocation before any live disclosure path.
  3. P6 cloud Shell sandbox: strictly blocked by item 2 plus owner consent.
  4. P7 OAuth accounts, P8 GitHub/GitLab/Actions connectors with real scopes, P9 localization/accessibility review, P10 clean-machine Pop!_OS/Ubuntu matrix, repository license choice, and owner release approval.
- **Resume instruction:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run the two verification commands, then attempt item 1 or extend the existing modules (do not rewrite them).

---

### 2026-11-20 09:30 UTC — P8 GitHub connector slice added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/connectors/base.py` (capability matrix, `Grant`, `RepositoryProvider`), `boru/connectors/github.py` (official REST connector, grant-checked before any request, HTTPS by default, token only via env-var name), `tests/test_connectors.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **243 tests**. MOCK/STATIC only — no live GitHub call, no credential.
- **Security implications:** denied operations produce zero outbound requests; read-only profiles cannot write, dispatch, merge or release; call ceiling and expiry enforced; audit events carry no token or response body; a token is identity only.
- **Blocked:** live GitHub/GitLab pilots with real scopes, webhook ingress, self-hosted runner policy, and every other P5–P10 gate.
