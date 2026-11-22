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

---

### 2026-11-20 09:50 UTC — P2 OpenCode adapter and P9 localization added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/adapters/opencode.py` (official loopback client, disabled by default, real session-ID evidence), `boru/i18n.py` + dashboard localization for EN/TR/DE, `tests/test_opencode_adapter.py`, `tests/test_i18n.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **258 tests**; `boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. MOCK/STATIC only.
- **Security implications:** the adapter is loopback-only and cannot modify OpenCode's configuration or sessions; the dashboard translates fixed labels only; a live OpenCode child-session pilot remains HOLD.

---

### 2026-11-20 10:15 UTC — persistent consent store added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/consent.py` (`ConsentStore` — SQLite-backed grants, nonce replay protection, revocation, expiry, owner-only file mode 0600) and `tests/test_consent_store.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **269 tests**. MOCK/STATIC only.
- **Security implications:** revoked and expired grants stay denied after a restart; a nonce can be used once; only bounded identifiers and timestamps are stored (no tokens, paths or model output). Broker worker authentication and OS confinement remain HOLD.

---

### 2026-11-20 10:40 UTC — OAuth/PKCE flow and token handle vault added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/auth/pkce.py` (S256 verifier/challenge, state, nonce, constant-time compare), `boru/auth/oauth.py` (`OAuthClientConfig`, `OAuthFlow` with a bounded loopback redirect listener and state/error verification), `boru/auth/tokens.py` (`TokenVault` opaque handles, 0600 metadata file), `tests/test_oauth.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **287 tests**; OAuth redirect capture verified against a test-owned loopback endpoint. MOCK/STATIC only.
- **Security implications:** HTTPS-only endpoints, numeric-loopback redirect, single-use state and nonce, opaque token handles only (no token values anywhere), and no claim of a connected provider or of inference entitlement.
- **Blocked:** real provider registration/consent, live OAuth round trip, and all remaining live gates.

---

### 2026-11-20 10:50 UTC — Round handoff (commit `971140e`, CI run 34 success)

- **Verified at this commit:** `scripts/check_project.py` PASS; `python3 -m unittest discover -s tests` PASS **287 tests**; `boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. All MOCK/STATIC.
- **Implemented and unit/integration-tested (source level):** P1 core contracts/states/state-store/CLI/providers; P2 optional loopback OpenCode adapter; P3 mode-aware routing and bounded policy-safe fallback; P4 DAG planner with counted leases; P5 fail-closed disclosure gate + persistent consent store; P7 cloud transport, OAuth/PKCE flow, token handle vault; P8 grant-bound GitHub connector; P9 loopback dashboard with EN/TR/DE labels; P10 user-space install/rollback round trip.
- **Remaining HOLD with exact next actions:**
  1. Live Jan 3-turn pilot — start Jan's local API server (still not listening in this session), then follow `docs/JAN_PILOT.md` with an owner-confirmed endpoint, local model ID and tools-disabled setting.
  2. Live OpenCode child-session pilot in a disposable profile (real session ID, provider/model).
  3. Provider registration + live OAuth round trip for one provider (identity vs inference verification).
  4. Broker hardening: authenticated worker identity, OS confinement, independent security review.
  5. Cloud Shell sandbox (blocked by item 4 + owner consent).
  6. Live GitHub/GitLab/Actions scoped pilots, webhook ingress policy.
  7. Dashboard accessibility review and remaining localization polish.
  8. Clean-machine Pop!_OS/Ubuntu acceptance matrix, repository license choice, owner release approval.
- **Resume:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run the two verification commands, then attempt item 1 or the next source-only slice. Do not rewrite existing modules; extend them.

---

### 2026-11-20 11:10 UTC — budget, cooldown and context-bound slice added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/budgets.py` (labelled estimates, reservation + observed-usage recheck, cost refusal, `CooldownTracker`, deterministic `compact()`), core integration plus config `cooldown_seconds` / `max_context_chars`, `tests/test_budgets.py` and updated core budget tests.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **302 tests**. MOCK/STATIC only.
- **Security implications:** over-ceiling work never produces an extra call or a wider permission; an unbounded cost is refused rather than guessed; unknown usage stays unknown; cooldown never switches to a broader candidate. No billed provider call was made.

- **CI run 36 on `8053d7f` FAILED** (`Run dependency-free contract tests`): the OAuth redirect tests bound a port in a probe server, closed it, then re-bound it in the flow. On the slower shared runner that rebind lost the race and the listener refused to bind, so the capture tests errored. **Fixed in `b7d79b9`**: the listener now binds an ephemeral port when the configuration uses port 0, reports the actual port on the attempt before the capture, and a busy port fails closed with `PolicyViolation`. OAuth tests now run in ~2s instead of ~30s. `scripts/check_project.py` and the full suite (303 tests) PASS locally after the fix; CI must be re-verified for `b7d79b9` before claiming green.

- **CI re-verified after the fix:** run 40 (https://github.com/Tihulu/Tihulu-Boru-Yolu/actions/runs/44774916466) on `30b9b3a` and run 39 on `b7d79b9` both **success**. Earlier failures (run 36–38) were the redirect-port race described above, now fixed and covered by an explicit busy-port test.

---

### 2026-11-20 11:40 UTC — opt-in Jan discovery and health probe (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `JanProvider.discover_models()` / `health()` behind an explicit `allow_discovery` flag, config + core wiring, `JanDiscoveryTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **309 tests**. MOCK/STATIC only.
- **Security implications:** discovery is off by default because a Jan endpoint may also proxy remote providers; only allowlisted IDs are reported; `health()` returns a count, not an inventory; no live endpoint was called.

---

### 2026-11-20 17:35 UTC — Round handoff (commit `1a5564f`, CI run 41 success)

- **Verified at this commit:** `scripts/check_project.py` PASS; `python3 -m unittest discover -s tests` PASS **309 tests**; `boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`; installer round trip on a temporary directory. All MOCK/STATIC.
- **CI note for the next session:** two earlier runs failed on a redirect-port race in the OAuth tests, fixed in `b7d79b9` (ephemeral loopback port, reported before capture, busy port fails closed). Runs 39, 40 and 41 are green.
- **Remaining HOLD with exact next actions:** (1) live Jan 3-turn pilot — start Jan's local API server, then `docs/JAN_PILOT.md` with an owner-confirmed endpoint, model ID and tools-disabled setting; (2) live OpenCode child session; (3) provider registration + live OAuth round trip; (4) broker hardening + independent security review; (5) cloud Shell sandbox; (6) live GitHub/GitLab/Actions scoped pilots; (7) accessibility review and localization polish; (8) clean-machine Pop!_OS/Ubuntu matrix; (9) license choice; (10) owner release approval.
- **Resume:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run the two verification commands, then attempt item 1 or extend the existing modules.

---

### 2026-11-20 18:00 UTC — GitLab connector added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/connectors/gitlab.py` (official `/api/v4` connector, same grant boundary as GitHub), `GitLabProvider` tests.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **315 tests**. MOCK/STATIC only — no live GitLab call, no credential.
- **Security implications:** denied operations make zero outbound requests; read-only profiles cannot write/merge/release; token only via an environment-variable name; audit events carry no token or response body.

---

### 2026-11-20 18:30 UTC — LIVE Jan pilot PASSED (commit on `p1/boru-core-vertical-slice`)

**Evidence class: LIVE** (real local inference through Boru Core, TIHULU-AUTO absent, no OpenCode/Kandev/Langflow involved).

- **Endpoint/model used:** loopback Jan server, `Jan-v3_5-4B-Q4_K_M` (explicit allowlist entry, loopback endpoint from the owner's own server, server-side tool execution disabled by configuration).
- **Run 1 (`chat-1`, 3 turns, synthetic memory check):** state `REVIEW` -> explicit owner review -> `DONE`; `provider=jan`, `model_id=Jan-v3_5-4B-Q4_K_M`, `evidence_class=direct` preserved after the review, `usage_if_observed` = input 48 / output 2 / total 50. The model returned the single word it was asked to remember.
- **Run 2 (`chat-2`, 3 turns, synthetic numeric check):** `REVIEW`, `direct`, same provider/model identity, usage 48/2/50 (usage observed and consistent).
- **Run 3 (`chat-3`, 3 turns, single-word check):** `REVIEW`, `direct`, usage 43/2/45.
- **Negative check (allowlist):** a task naming a model outside the allowlist produced `HOLD`/`missing_provider` **with no provider call** (previously it was silently substituted — see the defect below).
- **Defect found and fixed during the live run:** (a) `Router.decide` honoured a task-level `selected_provider`/`selected_model` only in `MANUAL` mode, so a task-level selection in `AUTO` was silently overridden — the selection now binds the dispatch in every mode and an unpermitted selection is refused; (b) `ModelRegistry.candidates` accepted a *partial* capability-tag match, so a required tag could be ignored — tags must now all match; (c) the Jan transport now supports an explicit `model_response_is_path` option, because the live endpoint reports the on-disk model path rather than the model ID; identity is still verified (an exact ID match, or a path containing `/<id>/`). No local path, file content, device inventory or credential was recorded anywhere.
- **Still HOLD:** OpenCode child-session pilot, provider OAuth round trip, broker/OS isolation and security review, cloud Shell, GitHub/GitLab/Actions scoped pilots, clean-machine Pop!_OS/Ubuntu matrix, license, owner release approval. `live_acceptance` output stays `HOLD` until the owner reviews each task.

---

### 2026-11-20 19:20 UTC — LIVE OpenCode child-session pilot PASSED (commit on `p1/boru-core-vertical-slice`)

**Evidence class: LIVE** (real child session through the owner's own local OpenCode server, via the official authenticated CLI).

- OpenCode version **2.3.2** on Pop!_OS, background service on `127.0.0.1` (`opencode service status`); its HTTP API requires authentication, so no token was harvested: the pilot was driven with the official `opencode api` command, which performs discovery and authentication itself.
- **Child session:** id `ses_e058f2362ffeN0ZsdI1BLe7ZpH`, project `6dd2ba087fc647b4e1b07da3feecea0986412904`, created in a **disposable pilot directory** that is git-ignored by this repository.
- **Assistant reply evidence:** message id `msg_1fa70f0ff001TB43YpT5L9puuQ`, agent `build`, model id `tidepool-alpha-free`, provider id `opencode`, finish `stop`, cost 0, tokens input 14213 / output 2 / reasoning 87, reply text `blue` to a synthetic one-word question.
- **Not a skill load and not a simulation:** the provider/model identity and message id came from the live server response.
- **Cleanup:** both pilot sessions (`ses_e058f2362ffeN0ZsdI1BLe7ZpH`, and an earlier one whose disposable directory did not exist) were deleted through the official API; no global agent, provider or configuration was modified, and no other session was touched.
- **Boru adapter status:** `boru/adapters/opencode.py` remains source-tested only. Live integration through the adapter needs the owner to authorize the auth material (it accepts an environment-variable name); the CLI handled authentication for this pilot, so the adapter's live path stays HOLD.

---

### 2026-11-20 20:00 UTC — broker authorization slice added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/broker.py` (operation allowlist, resource aliases with escape/symlink refusal, worker scopes, replay-protected nonces, `AuthorizationReceipt`) and `tests/test_broker.py` (negative paths: unknown operation, undeclared/traversing/symlinked resource, worker without scope, missing/expired/revoked grant, replayed nonce, malformed request, no consent store).
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **339 tests**. MOCK/STATIC only.
- **Security implications:** nothing is executed; every denial path is closed and receipts carry alias names, never raw paths or file contents. The executor, OS confinement and an authenticated persistent worker store remain HOLD pending independent security review.

---

### 2026-11-20 20:40 UTC — bounded local worker added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/executor.py` (`LocalExecutor` — alias-confined read-only acquisition returning typed fields only; `O_DIRECTORY|O_NOFOLLOW`; receipt-bound) and `tests/test_executor.py`; receipt validation now rejects an operation outside the allowlist.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **350 tests**. MOCK/STATIC only.
- **Security implications:** `list_dir_alias` returns a count, never names; `read_file_alias` reports size, never content; requesting `content`/`raw_stdout`/`file_contents` is refused; expired or forged receipts are refused; symlinked aliases are refused at construction. No subprocess, shell, network or mutation exists in this worker, and no live restricted operation was run.
- **Still HOLD:** an authenticated persistent worker store, live socket, OS confinement, mutating/subprocess operations, L2 excerpt release and independent security review.

---

### 2026-11-20 21:30 UTC — local rejection ledger added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/audit.py` (`RejectionLedger` — append-only, bounded, owner-confined SQLite sink with 12 fixed categories and sanitized fields) and `tests/test_audit.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **362 tests**. MOCK/STATIC only.
- **Security implications:** audit rows carry no payload, path, token or provider text; there is no update/delete API; retention is bounded and prunes only the oldest rows; the file is 0600 inside an owner-named directory; group/world-writable directories and symlinked paths are refused.

---

### 2026-11-20 22:00 UTC — rejection ledger wired into real denial paths (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `BoruCore` and `Broker` accept an optional `RejectionLedger` (in-memory by default, durable file on request); `LedgerWiringTests` assert the recorded rows.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **367 tests**. MOCK/STATIC only.
- **Security implications:** denied submissions and holds now produce sanitized local audit rows; no task goal, path, file content, token or provider text is ever recorded. Connector and disclosure denials are recorded by their own layers where a ledger is supplied; remaining paths stay HOLD.

---

### 2026-11-20 23:15 UTC — ledger shared by all layers + durable `--audit-dir` (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `DisclosureGate`, `GitHubProvider`, `GitLabProvider` accept an optional ledger and record their denials; CLI gained `--audit-dir` for a durable owner-directory ledger; `LedgerWiringExtendedTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **371 tests**; a CLI run with `--audit-dir` produced one sanitized `scheduler/budget_exceeded_pre_dispatch` row in a 0600 file. MOCK/STATIC only.

---

### 2026-11-20 23:40 UTC — dashboard review queue and audit view (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** dashboard routes `/queue` and `/audit`, an audit section in the root page, an `audit` label for EN/TR/DE, and `DashboardAuditTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **385 tests**. MOCK/STATIC only.
- **Security implications:** the audit view shows bounded rows only (category, subject, reason, detail kind, timestamp) and no goal, path, content or token; no ledger means an empty list, never a crash; the dashboard stays loopback-only.

---

### 2026-11-21 00:20 UTC — cross-boundary tracer added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/boundary.py` (`Classification`, `CrossBoundaryGuard`), config `classifications` + core enforcement before any Jan/cloud dispatch, `examples/core.example.json` declares its local direction, `tests/test_boundary.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **399 tests**. MOCK/STATIC only.
- **Security implications:** an outbound request without a declared classification is refused with no network call (`HOLD/unclassified_boundary`, recorded in the ledger); data class above the declared one, and a grant mismatch, are denied; in-process providers need no crossing.

---

### 2026-11-21 01:00 UTC — `boru audit` command (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** CLI `audit` subcommand (`--audit-dir`, `--limit`) and `AuditCommandTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **404 tests**. MOCK/STATIC only.
- **Security implications:** prints bounded rows only; `--audit-dir` must name an existing directory; no payload, path, content or token appears in output.

---

### 2026-11-21 01:30 UTC — `boru plan` and `boru queue` commands (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** CLI `plan` (submit a dependency-aware plan, dispatch what is ready, resumable) and `queue` (tasks awaiting explicit review); `submit_plan` now resumes existing tasks instead of failing on a re-run; `PlanAndQueueCommandTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **410 tests**. MOCK/STATIC only.
- **Security implications:** a dependent task never runs before its dependency is explicitly reviewed and `DONE`; no goal, path, content or token is printed.

---

### 2026-11-21 01:45 UTC — Consolidated state (commit `e9149f3`, CI run 50 success)

**Verified at this commit:** `python3 scripts/check_project.py` PASS · `python3 -m unittest discover -s tests` PASS **410 tests** (baseline 21 + 389 added) · `python3 -m boru demo --show-text` -> `REVIEW` / `simulated` / `live_acceptance=HOLD` · installer round trip on a temporary directory. All MOCK/STATIC unless a live entry says otherwise.

**Implemented + unit/integration-tested (source):**
- P1 `boru/` core: `types` (TaskEnvelope/AgentResult, schema 1, unknown- and private-field rejection), `policy` (four orthogonal axes, safe LOCAL_ONLY default), `state`, `queue` (bounded, replay-protected), `registry` (explicit locality, declared cost/quality tiers), `store` (SQLite, 0600, single writer, CAS), `config`, `core`, `cli` (`demo`, `run`, `status`, `cancel`, `review`, `providers`, `audit`, `plan`, `queue`).
- Providers: `mock` (simulated), `jan` (loopback-only, explicit allowlist, tools disabled, `tool_choice:none`, bounded bytes, `model_response_is_path` option) and `cloud` (HTTPS-enforced, credential only via env-var name, honest `configured`/`authenticated` state).
- P3 `router.py` (mode ranking + bounded policy-safe fallback) and `budgets.py` (labelled estimates, pre-dispatch reservation, observed-usage recheck, cost refusal, cooldowns, bounded compaction).
- P4 `scheduler.py` (≤6 logical agents, DAG, counted leases, default one large local model).
- P5 `privacy.py` + `consent.py` + `broker.py` + `executor.py` + `audit.py` (fail-closed gate, persistent consent, scoped authorization, bounded read-only worker, shared append-only ledger wired into every denial path).
- P7 `auth/` (official authorization-code + PKCE, loopback redirect capture, opaque token handles).
- P8 `connectors/` (GitHub REST + GitLab v4, grant-bound, zero-request denials).
- P9 `dashboard.py` (loopback `/`, `/status`, `/task/<id>`, `/queue`, `/audit`, `POST /review`) + `i18n.py` (EN/TR/DE).
- P10 `scripts/install_boru.sh` / `uninstall_boru.sh` (user-space, dry-run, owner-only state, rollback tested).
- Cross-boundary tracer (`boundary.py`): outbound requests must be declared.

**LIVE evidence:** A21 (Boru Core -> direct Jan, three three-turn conversations, provider/model/usage recorded, owner review to DONE, non-allowlisted model refused with no call) and A23 (real OpenCode child session with session/message ids, agent, model and provider identity; sessions deleted afterwards).

**Remaining HOLD with exact next actions:**
1. Broker hardening: authenticated persistent worker identity store, live socket, OS confinement; then independent security review (P5 live gate).
2. P6 cloud Shell sandbox: strictly blocked by item 1 plus explicit owner consent.
3. Provider registration + live OAuth round trip (identity vs inference verification).
4. Live GitHub/GitLab/Actions scoped pilots (needs owner-approved scopes in a disposable repository) and webhook ingress policy.
5. Dashboard accessibility review and localization polish.
6. Clean-machine Pop!_OS 24.04 and Ubuntu LTS acceptance matrix, including offline and partial-outage runs.
7. Repository license choice and owner release approval.

**Resume instruction:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run the two verification commands above, then attempt item 3 or the next source-only slice. Do not rewrite existing modules; extend them.

---

### 2026-11-21 02:15 UTC — worker identity registry added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/workers.py` (`WorkerRegistry`, `WorkerRecord` — owner-created identities, bounded lifetimes, 0600 secret files, constant-time validation, revocation, persistence) and `tests/test_workers.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **422 tests**. MOCK/STATIC only.
- **Security implications:** secrets never leave the owner-only file; revoked or expired identities never authorize; no API returns or logs a secret; the identity record is explicitly not a security boundary — host authentication, OS confinement and an independent security review remain HOLD.

---

### 2026-11-21 02:45 UTC — end-to-end local disclosure pipeline (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/pipeline.py` (worker + broker + executor + gate + ledger in one local, fail-closed flow), L0/L1 field mapping aligned with `boru/executor.py`'s typed fields, and `tests/test_pipeline.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **432 tests**. MOCK/STATIC only.
- **Security implications:** every denial path (missing/expired/wrong-operation grant, revoked worker, L2 under MINIMUM_NECESSARY, field not produced) fails closed *before* data is released; successes return typed fields only; raw content, file names, paths and listings are never produced; each step is recorded in the ledger. No cloud call is made and no live boundary is claimed.

---

### 2026-11-21 03:15 UTC — dashboard accessibility (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** semantic dashboard markup (`<html lang>`, `aria-labelledby` sections, `<caption>`, labelled review form, no JS), an `accept` label for EN/TR/DE, and `DashboardAccessibilityTests`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **444 tests**. MOCK/STATIC only.
- **Security implications:** none — presentation only; the review action still requires an explicit `accept: true`.

---

### 2026-11-21 04:00 UTC — Cloud-Shell grant contract (decisions only) added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/sandbox.py` (`SandboxGrant` bound to grant id/owner/recipient provider+model/task/sandbox id/operation types/resource aliases/field disclosures/expiry/call ceiling/nonce; `SandboxBroker` with the full denial set and a call-ceiling ordering) and `tests/test_sandbox.py`; `docs/SECURITY_MODES.md` records the split.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **455 tests**. MOCK/STATIC only.
- **Security implications:** denied paths never execute anything and are recorded; host-level Shell is absent from the allowlist; non-traversing resource aliases; the sandbox runtime is not implemented, so P6 remains blocked pending P5 live acceptance and explicit owner consent.

---

### 2026-11-21 04:30 UTC — sanitized evidence report added (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `scripts/evidence.py` (static manifest + full unit suite + offline demo + install/run/uninstall round trip, sanitized output, exit 0 only when every mandatory check passes), docs updates, `tests/test_evidence.py`.
- **Observed locally:** `python3 scripts/evidence.py` -> exit 0 with `unit_tests: ('PASS', 455)` and `install: {install, demo, uninstall} = PASS`; the report contains no private path, credential or device inventory. MOCK/STATIC only.

- **Defect found and fixed during the evidence work:** the first version of `tests/test_evidence.py` invoked the report without a `--quick` flag, and the report runs the whole unit suite, so each test re-ran the suite that contained it — one run took 45 minutes. `scripts/evidence.py` gained `--quick` (static check + offline demo only, install/unit steps reported as SKIPPED) and the tests use it; the evidence tests now run in ~0.4s and the full suite is 459 tests. The full report still runs everything and exits 0 on this machine.

---

### 2026-11-21 04:45 UTC — README reflects the implemented state (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** README "Status" now states what is implemented and tested locally, which live gates have passed (A21, A23) and what stays HOLD; added a "What you can run today" command block; the Codex handoff section points at draft PR #14 and `p1/boru-core-vertical-slice`. Added `TranslationCompletenessTests` so a missing or empty label in any of en/tr/de fails the suite.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **461 tests**. MOCK/STATIC only.

---

### 2026-11-21 05:15 UTC — provider capability/auth matrix (issue #10/#11 phase 1) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `docs/AI_PROVIDER_CONNECTIONS.md` (capability/auth/billing matrix for OpenAI, Claude, Google/Gemini+Vertex, GLM, Kimi, DeepSeek, NVIDIA, Grok/xAI and Jan; what Boru never does; the secret-free example config), `scripts/check_project.py` manifest extended, README-style cross references, and acceptance row A31.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **461 tests**. STATIC only.
- **Security implications:** the matrix states explicitly that consumer Google-login inference and third-party Claude subscription login are not offered, that credentials only appear as environment-variable names, and that no provider account is connected by this repository.

---

### 2026-11-21 05:45 UTC — clean-machine acceptance matrix and rollback checklist (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `docs/OS_ACCEPTANCE.md` (M01–M12 on Pop!_OS 24.04 and Ubuntu 24.04 LTS x86_64, pre-flight, rollback checklist, out-of-scope list), manifest extended, cross references, ACCEPTANCE note.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **461 tests**. STATIC only.
- **Status:** every row starts HOLD; no clean-machine run has been performed by this repository. The only live evidence remains A21 and A23 on the owner's development host.

---

### 2026-11-21 06:00 UTC — round close: source slices, documents and evidence complete (commit `3100b16`, CI run 58 success)

- **Branch / PR:** `p1/boru-core-vertical-slice`, draft PR #14 against `plan/architecture-security-profiles-ubuntu-popos` (base of still-open draft PR #1). `main` untouched, nothing merged.
- **Verified:** `scripts/check_project.py` PASS · `python3 -m unittest discover -s tests` **461 tests PASS** · `python3 scripts/evidence.py` exit 0 · `boru demo` -> `REVIEW` / `simulated` / `live_acceptance=HOLD`. All MOCK/STATIC unless a live entry says otherwise.
- **Live evidence:** A21 (direct Jan 3-turn conversations: provider/model/usage recorded, owner review to DONE, non-allowlisted model refused with no call) and A23 (real OpenCode child session: session/message IDs, agent, model, provider; both pilot sessions deleted afterwards).
- **Remaining HOLD, in order, with the exact next action:**
  1. Broker hardening: host-level process authentication, transport encryption and OS confinement; then an **independent security review** (P5 live gate). Code-level progress made: `boru/broker_service.py` (loopback, identity-authenticated, bounded) plus broker/registry identity checks. Next action: schedule the review with that chain.
  2. Remote Privacy Bridge half: a real cloud recipient and L2 excerpt release. Next action: only after item 1.
  3. Provider registration + live OAuth round trip (identity vs inference verification). Next action: register with one provider, pilot with `boru/auth/`.
  4. P6 sandbox runtime: `boru/sandbox.py` decides but executes nothing. Next action: only after items 1–2 and explicit owner consent.
  5. Live GitHub/GitLab/Actions scoped pilots (needs owner-approved scopes in a disposable repository) and webhook ingress policy. Read-only live endpoint verification for this repository passed 2026-11-21 (see `harness/build-log.md`); write/action pilots remain HOLD.
  6. Clean-machine Pop!_OS 24.04 and Ubuntu 24.04 LTS x86_64 acceptance (M01–M12 in `docs/OS_ACCEPTANCE.md`), including offline and partial-outage runs.
  7. Dashboard localization/accessibility polish beyond what is implemented and tested.
  8. Repository license choice, then owner release approval.
- **Resume instruction:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run `scripts/evidence.py`, then attempt item 3 or the next source-only slice. Extend existing modules; do not rewrite them.

---

### 2026-11-21 06:30 UTC — P5 hardening: authenticated broker surface (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/broker_service.py` (loopback-only, identity-authenticated, single-request-per-connection, bounded and idle-timed authorization service), broker now consults `WorkerRegistry` (revoked/expired/unknown/secret-mismatch identities deny), pipeline uses the registry, `ConsentStore(thread_safe=True)` so the service can share it, `tests/test_broker_service.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **469 tests**. MOCK/STATIC only.
- **Security implications:** denied identities deny before any other check; the service cannot bind a non-loopback address or start without a secret; nothing executes an operation. Host-level process authentication, transport encryption, OS confinement and independent security review remain HOLD, so this is explicitly **not** a security boundary.
- **Defect fixed while wiring this:** `ConsentStore`'s `thread_safe` flag was passed to sqlite as `check_same_thread=thread_safe`, i.e. inverted — thread-safe mode *enforced* the same-thread rule and crashed under the service. Now `check_same_thread=not thread_safe`, with a guard around every read/write.

---

### 2026-11-21 07:15 UTC — owner-run OAuth connection flow (P7 item) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/connect.py` (`boru connect` / `accounts` / `disconnect` commands), `OAuthClientConfig` gained an explicit `allow_http_endpoints` opt-in, `OAuthFlow` honours it, and `TokenVault` now **loads** its persisted handles (it previously only wrote them), with the same owner-only and bounded checks.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **478 tests**. MOCK/STATIC only.
- **Security implications:** the flow stores only an opaque handle, never prints or logs a token, reports `authenticated` with `model_test_passed: false`, and requires a loopback redirect. Registration with a real provider is an owner action; no provider is connected by this repository.
- **Defects fixed while testing:** (a) `TokenVault` wrote but never read its metadata, so revocation did not survive a new process; (b) `connect` raised during constructor-time validation instead of returning a configuration error; (c) the loopback delivery raced with listener bind in tests, now retried.

---

### 2026-11-21 08:00 UTC — connector request-scope hardening (issue #15) + live endpoint verification (commit on `p1/boru-core-vertical-slice`)

- **Security finding fixed (issue #15):** the grant check considered only the operation, so a granted read could name another repository or reference, and the public `call()` surface accepted arbitrary `method`/`path` overrides. Both providers now call `boru/connectors/scope.py` before any transport is constructed: repository and reference binding, refusal of `path`/`method` overrides, per-slot charset and segment validation, an explicit reference for file reads, and an explicit denial of account-wide `list_repositories` with a repository-scoped grant.
- **Live verification (read-only, owner-approved, this repository):** the official endpoints the connector builds were exercised through the GitHub CLI against `Tihulu/Tihulu-Boru-Yolu`: `/repos/{owner}/{repo}/issues`, `/repos/{owner}/{repo}/pulls/1`, `/repos/{owner}/{repo}/pulls/1/reviews`, `/repos/{owner}/{repo}/branches`, `/repos/{owner}/{repo}/commits/f90fd3ed…`, `/repos/{owner}/{repo}/actions/workflows` and `/user` all returned HTTP 200. No write, dispatch, secret or credential was used.
- **Test fixtures corrected:** the GitLab synthetic grants named a different repository than their requests (the exact mismatch that made the bypass possible); they are now scoped to the repository they request.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **494 tests** (16 new scope tests). MOCK/STATIC only.
- **Still open, recorded not implemented:** response-level reference validation, workflow-specific authorization, redirect/header review, special encoding for unusual repository names, and token/account identity verification. The connector is not yet a security boundary.

---

### 2026-11-21 08:30 UTC — same-machine HOME isolation test (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `tests/test_home_isolation.py` (install/run/uninstall under a scratch `HOME`, sentinel outside the named paths untouched, `state` 0700, launcher 0755, nothing written outside the named directories) and a note in `docs/OS_ACCEPTANCE.md` that this is not a clean-machine acceptance.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **498 tests**. MOCK/STATIC only.
- **Honest scope:** this proves the installer touches only the named directories on *this* machine with *this* Python. It cannot prove a fresh-image install, offline behaviour, partial outages or rollback, so M01–M12 remain HOLD.
- **Behaviour confirmed and documented:** uninstall removes the launcher and the named directories but leaves a possibly user-owned `--bin-dir` itself (empty) in place.

---

### 2026-11-21 09:00 UTC — review pass: import hygiene and stale counts (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** removed unused imports across the package (typing names, `tempfile` in the store, `stat`/private helpers in the executor, `field`/`LOCAL_PROVIDERS` in the registry, routing/state/scheduler/cli names, `MAX_MESSAGE_CHARS` in the Jan transport, `ConnectorDenied` in the connector base, `ipaddress` in the cloud transport, `bounded_text` in the auth flow); refreshed stale test counts in README and `docs/ACCEPTANCE.md` (459/225 → 498).
- **Tests observed:** `scripts/check_project.py` PASS; `python3 -m compileall -q boru` clean; `unittest discover -s tests` PASS **498 tests**. No behaviour change: import and documentation only.

- **Review pass findings fixed:** README did not document `boru cancel`, and the connection/accounts/disconnect trio was not described in `docs/BORU_CORE.md`. Verified separately: every markdown link resolves, the 25-document manifest is complete, and no dead TODO/FIXME remains in the package (only documented interface stubs). CI run for `9a98ed6` re-verified green after this pass.

---

### 2026-11-21 09:30 UTC — connector transport hardening (issue #15 remaining gaps) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** both connectors now refuse redirects through a custom redirect handler (301/302/303/307/308 never followed), require a JSON or plain-text content type, bound the response body, and verify a `read_file` response's reference against the requested reference before returning it; `allow_http` is an explicit owner opt-in for pinned loopback test endpoints.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **502 tests** (4 new transport tests against a test-owned loopback endpoint). MOCK/STATIC only.
- **Defect found while wiring this:** an earlier patch silently overwrote the GitHub provider's content-type check with the redirect fix; the regression test now covers it.

---

### 2026-11-21 10:15 UTC — workflow binding and typed repository encoding (issue #15 final gaps) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** grants may declare ``workflow_ids``; `dispatch_workflow`, `configure_workflow` and `rerun_workflow` outside that list are denied before any request; a typed ``RepositoryRef`` parses exactly two non-traversing segments and percent-encodes them per provider (GitHub slash form, GitLab ``%2F``) replacing a naive string replace; connector tests updated to declare the workflows they use.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **507 tests** (5 new tests). MOCK/STATIC only.
- **Defects found and fixed while wiring this:** a stray ``@dataclass`` decorator landed on a helper function and a later fix removed the real one from ``Grant`` (both caught by the suite immediately); the typed encoding was called as a bare name instead of a method in one provider.

---

### 2026-11-21 10:45 UTC — token/account identity verification (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** ``verify_identity(expected_account)`` on both connectors reads the official account endpoint through the same hardened transport and matches the returned login/username against the grant's account; ``IdentityVerificationTests`` cover match, mismatch, missing token, bad account and malformed response.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **513 tests**. MOCK/STATIC only.
- **Security implications:** a token is reported as identity only; a mismatched account is ``identity_mismatch`` and never proceeds; a missing token is only ``configured``. No credential is printed or logged.

---

### 2026-11-21 11:15 UTC — workflow discovery and dispatch-input validation (issue #9) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/connectors/workflows.py` (`WorkflowSummary`, `parse_workflows`, `validate_dispatch_inputs`), `GitHubProvider.list_workflows_typed` (grant-checked discovery through the official endpoint), and `tests/test_workflows.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **525 tests**. MOCK/STATIC only.
- **Security implications:** discovery is grant- and repository-bound and refuses a non-granted repository before any request; dispatch inputs are validated before any dispatch is attempted, and an undeclared input schema is refused rather than guessed. No live workflow was dispatched, no secret or credential was used, and no listener was opened.

---

### 2026-11-21 11:45 UTC — localhost polling sync (issue #8) (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/connectors/polling.py` (`EventAllowlist`, `SyncEvent`, `PollingSync`) and `tests/test_polling.py`.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **533 tests**. MOCK/STATIC only.
- **Security implications:** the module imports no socket, server or threading primitive (a test asserts this), an empty allowlist accepts nothing, event ids are processed once with a bounded restart-safe seen-set, and undeclared or malformed events are refused rather than worked on. No webhook listener, ingress endpoint or credential is used.

---

### 2026-11-21 11:45 UTC — round close: source slices complete, PR description current (commit `a1a9ff6`, CI run 68 success)

- **Repository state:** branch `p1/boru-core-vertical-slice`, draft **PR #14** against `plan/architecture-security-profiles-ubuntu-popos` (base of still-open draft PR #1). `main` untouched, nothing merged. PR #14 now describes the current state: 96 changed files, +15,448/−14, 533 tests.
- **Verified at this commit:** `scripts/check_project.py` PASS · `unittest discover -s tests` **533 tests PASS** · `scripts/evidence.py` exit 0 · CI `Source-only contract checks` green on every commit. All MOCK/STATIC unless noted.
- **Live evidence:** A21 (Boru Core → direct Jan, three three-turn conversations: provider/model/usage recorded, owner review to DONE, non-allowlisted model refused with no call) and A23 (real OpenCode child session: session/message IDs, agent, model, provider; both pilot sessions deleted).
- **Open issues addressed at code level:** #8 (connectors + polling sync), #9 (workflow discovery + dispatch-input validation), #15 (all listed connector limitations), #12/#13 (Boru Core slices), #10/#11 (provider connector + connection flow + matrix doc).
- **Source work remaining: none identified.** Every remaining item needs an owner approval or a human action:
  1. Independent security review of the broker/worker/executor/connector chain (host process authentication, OS confinement, transport encryption).
  2. Real provider registration + live OAuth round trip.
  3. Disposable repository with scopes for a live GitHub/GitLab/Actions pilot.
  4. Clean-machine Pop!_OS 24.04 / Ubuntu 24.04 x86_64 runs of M01–M12 (including offline and partial-outage cases).
  5. Repository license choice and owner release approval.
- **Resume instruction:** check out `p1/boru-core-vertical-slice`, read `docs/BORU_CORE.md` and this entry, run `scripts/evidence.py`, then take the first owner-approved gate above. Do not rewrite existing modules; extend them.

---

### 2026-11-21 12:15 UTC — Jan lifecycle gap verified and recorded (commit on `p1/boru-core-vertical-slice`)

- **Verified against official documentation:** Jan's local API server exposes only the OpenAI-compatible `/v1/models` and `/v1/chat/completions` endpoints, with model loading managed from the Jan UI. There is **no documented model unload/lifecycle endpoint**.
- **Decision recorded:** Boru Core therefore does **not** implement a Jan unload adapter (an undocumented endpoint would also risk interrupting an unrelated Jan session). Resource management stays lease bookkeeping: counted logical-agent and large-model leases, refusal when exhausted, release of only Boru-owned leases.
- **Consequence:** issue #7's "unload only owned idle models" item is closed as *by design HOLD*, blocked on a documented Jan API or an explicit owner-approved manual action. Measured RAM/VRAM stays HOLD for the same reason.

---

### 2026-11-21 12:45 UTC — disclosure pipeline runs over the authenticated surface (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `boru/pipeline.py` now routes broker authorization through an authenticated loopback `BrokerService` when an endpoint is configured (identical flow, in-process otherwise), and `PipelineOverServiceTests` exercise the real socket end to end.
- **Tests observed:** `scripts/check_project.py` PASS; `unittest discover -s tests` PASS **556 tests**. MOCK/STATIC only.
- **Security implications:** the identity handshake is part of the tested path; a wrong secret, a revoked worker, a missing grant, L2 under MINIMUM_NECESSARY and a field the operation does not produce all deny before data is released; every denial is recorded in the ledger. Still not a security boundary: host process authentication, OS confinement and independent review remain HOLD.

---

### 2026-11-21 13:15 UTC — owner gate plan published (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `docs/OWNER_GATE_GUIDE.md` (the five remaining gates in order, each with a PASS definition, the owner action, the agent action and what it is blocked on) and `docs/SECURITY_REVIEW_REQUEST.md` (the Gate 1 review package: scope table, out-of-scope, reproduction commands, findings template, PASS criteria). Manifest extended to require both.
- **Tests observed:** `scripts/check_project.py` PASS (25 documents); `unittest discover -s tests` **556 tests PASS**. MOCK/STATIC only.
- **Gate states:** 1 security review HOLD (reviewer needed), 2 provider OAuth HOLD (registration needed), 3 connector pilot HOLD (disposable repository needed), 4 clean-machine matrix HOLD (images needed), 5 license/release HOLD (owner decision).

---

### 2026-11-21 14:00 UTC — review package verified and published (commit on `p1/boru-core-vertical-slice`)

- **Changes made:** `docs/REVIEW_PACKAGE.md` — a self-contained review package for an external reviewer: repository/branch/PR/CI links, the exact reproduction commands with their observed results, 19 components with file links, a 57-item invariant checklist where every invariant points to the named test that asserts it, out-of-scope statements, the recorded live evidence (A21, A23), a findings template and PASS criteria. Manifest extended to require it.
- **Verification performed:** every referenced test name exists in the suite (57/57), every referenced file path exists (39/39), and the five documented commands were re-run on this head — `check_project.py` PASS, `unittest` 556 tests OK, `evidence.py` exit 0, `boru doctor` overall ok, `boru demo` REVIEW/simulated.
- **Gate 1 status:** still **HOLD** — the package is ready; the reviewer (GPT Astray, per the owner) is the missing party.

---

### 2026-11-22 — Gate 1 remediation in progress (commits `e449d17`, `79abd23` on `p1/boru-core-vertical-slice`)

**State: WORK IN PROGRESS — the tree is clean and committed; no uncommitted work exists.**

- **Context:** the external review of `cc73940` returned FAIL with findings F01–F22. The reviewer also supplied an executable regression probe file (20 probes); it is now checked in as `tests/test_review_regressions.py` so CI runs the same acceptance spec.
- **Closed in `e449d17`:** F01 (HMAC-signed, request-bound authorization receipts verified by the executor under the worker key), F02/F13 (worker ids stay single opaque segments; nonfinite stamps are never valid), F03/F11 (consent binds recipient, task, operation, alias, field and level; no downgrade into a wider level), F08 (component-wise `dir_fd` + `O_NOFOLLOW` target resolution), F09 (ledger identifiers validated and refused, never stored), F12 (grant ids immutable; a revocation cannot be reset by replacement), F14 (loopback service concurrency bounded), F17/F18 (used nonces bounded; read metadata real and bounded, never synthesized).
- **Closed in `79abd23`:** receipts name the resource only by an **opaque token** (`r-<16 hex>`) derived from the owner-declared path, so no alias or absolute path rides in a receipt; an alias may be a safe name **or** an owner-declared absolute path, and every path component is checked (intermediate symlinks refused); the broker's own worker identity bounds unauthenticated in-process requests; a consent grant may omit its alias (owner-explicit any-resource) while task/field/level/expiry/nonce binding stays mandatory.
- **Tests observed:** `unittest discover -s tests` **572 tests OK** at `e449d17`; broker/consent/executor/pipeline/service/workers modules OK at `79abd23`. MOCK/STATIC only.
- **Remaining (exact next action):** 18 of the 20 reviewer probes still fail. Fix in this order, one commit each with a regression test:
  1. `boru/workers.py` — `create(now=nan)` must persist a record that `valid()` refuses (probe: `test_worker_registry_cannot_issue_nonfinite_expiry`).
  2. `boru/privacy.py` — the in-memory `ConsentStore` must bind level (probe: `test_l0_owner_grant_cannot_authorize_l2_local`); `boru/consent.py` must refuse a re-issued revoked grant id (probe: `test_grant_revocation_cannot_be_erased_by_same_id_reissue`).
  3. `boru/connectors/scope.py` — reject NUL/control characters in slots; `rerun_workflow` must carry a granted `workflow`; add `check_dispatch_body` (body `ref` must equal the grant reference, inputs bounded) used **before** any transport (probes: `test_repository_slots_reject_nul`, `test_workflow_rerun_cannot_ignore_workflow_allowlist`, `test_workflow_dispatch_cannot_override_reference_in_body`).
  4. `boru/connectors/github.py` + `gitlab.py` — `?ref=` uses the granted reference slot; `call()` enforces the grant account identity once per provider when a token is configured; audit records never contain a URL path; error bodies capped (probes: `test_github_read_file_must_use_granted_reference`, `test_gitlab_read_file_must_use_granted_reference`, `test_github_call_must_enforce_account_identity`, `test_connector_audit_does_not_record_repository_paths`).
  5. `boru/connectors/polling.py` — bound the seen-event set (probe: `test_polling_does_not_replay_evicted_event_ids`).
  6. `boru/types.py` — recursive bounded validation rejecting nested `raw_stdout` (probe: `test_result_contract_denies_nested_raw_host_content`).
  7. `boru/core.py` — `evidence_class` derived from provider provenance, not a provider claim; outbound payload classified before dispatch.
  8. `boru/policy.py` — documented upper bounds for every axis value.
  9. Then: full `unittest`, `scripts/check_project.py`, `scripts/evidence.py`, `boru doctor`, re-pin `docs/REVIEW_PACKAGE.md` to the final SHA, update issues #13/#14, request the re-review.
- **Do not weaken while remediating:** LOCAL_ONLY / LOCAL_ISOLATED / MINIMUM_NECESSARY defaults, the four independent policy axes, or the typed field maps.

---

### 2026-11-22 — Gate 1 remediation complete for all review findings (commit `93fb0de` on `p1/boru-core-vertical-slice`)

- **Changes made (six commits):** `e449d17` signed receipts + alias/level/field consent + no-follow traversal + sanitized ledger + bounded service; `79abd23` opaque resource tokens + owner-declared aliases + broker-identity bounding; `8e0869b` level-bound consent, nonfinite identities, sanitized ledger records; `93fb0de` connector slot/workflow/dispatch binding, account identity enforcement, capped bodies, bounded polling registry, recursive typed-payload validation, evidence-class provenance, boundary payload classification, policy upper bounds.
- **Acceptance spec executed:** the reviewer's 20 probes, checked in as `tests/test_review_regressions.py`, now pass **20/20** inside the suite.
- **Tests observed:** `unittest discover -s tests` **596 tests OK**; `scripts/check_project.py` PASS; `scripts/evidence.py` exit 0; `boru doctor` overall ok / live_acceptance HOLD. MOCK/STATIC only.
- **Package re-pinned:** `docs/REVIEW_PACKAGE.md` now names head `93fb0de101ed8b01eda2cdbcc8c61e29385e7321`, the 596-test and 20-probe commands, a per-finding remediation table (F01–F22 → closing commit) and the new invariant rows.
- **Owner action required (blocking, not a defect):** the harness refuses `git push` in this session, so the CI run for `93fb0de` does not exist yet and the recorded CI link still points at the previous head's run. The package says so explicitly instead of linking a run that was never executed. Push + CI must be authorized by the owner, after which the link can be re-pinned.
- **Next action:** request the independent re-review of `93fb0de` (Gate 1). Gates 2–5 remain owner actions: provider registration/OAuth, disposable-repository connector pilot, clean-machine Pop!_OS/Ubuntu M01–M12, license and release approval.

---

### 2026-11-22 — Gate 1 package, re-review request and final verification state (commits `87d75d9`, `a076dc5`, `b46720f`)

- **Documents updated:** `docs/REVIEW_PACKAGE.md` (head re-pinned to the code head `87d75d91fa562729f0516e994a9a15ad965fe393`, 596-test and 20-probe commands, per-finding remediation table F01–F22 with closing commits, new invariant rows), `docs/SECURITY_REVIEW_REQUEST.md` (marked as a re-review of the remediated head), `docs/RE_REVIEW_REQUEST.md` (new: the ready-to-send reviewer request), `scripts/check_project.py` (manifest now requires both Gate 1 documents).
- **Verification observed on this head:** `scripts/check_project.py` PASS (28 documents), `unittest discover -s tests` **596 tests OK**, review probes 20/20, `scripts/evidence.py` exit 0, `boru doctor` overall ok / live_acceptance HOLD.
- **Blocking owner action:** the session harness refuses `git push`, so the CI run for this head does not exist and the package says so instead of linking a run that was never executed. Push authorization remains the owner's decision.

---

### 2026-11-22 — adversarial walkthroughs added; the broker refuses directory-reference targets (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed by this self-check:** `file_name` accepted `.` as a target name, so the broker could issue a receipt for a target that can never name an entry (the executor refused it later, fail-closed, but the contract now refuses it at the source). `boru/broker.py` refuses `.` and `..` targets.
- **New coverage:** `tests/test_adversarial_walkthroughs.py` (8 tests) drives the real broker/executor/consent/registry modules with control-character and path targets, symlinked targets, a key-less worker, a token bound to another resource, ambiguous grant ids and replayed nonces.
- **Tests observed:** `unittest discover -s tests` **604 tests OK**; reviewer probes 20/20; `scripts/check_project.py` PASS (28 documents). MOCK/STATIC only.

---

### 2026-11-22 — dead code removed from dispatch and the P5 documentation corrected (commit on `p1/boru-core-vertical-slice`)

- **Defect removed:** `boru/core.py::_run` carried an unreachable 28-line copy of the verification block after its early return; verification only ever ran through `_record`. The block is deleted (and the live path's always-true condition simplified). An AST scan of `boru/` now reports no unreachable statements.
- **Documentation corrected:** `docs/BORU_CORE.md` P5 section described the pre-remediation contract (unsigned receipts carrying alias names, `read_file_alias` without `line_count`, identity store and loopback surface listed as unimplemented). It now describes signed receipts, opaque resource tokens, real bounded read metadata, the worker registry and the loopback surface, and leaves only the genuine HOLDs.
- **Tests observed:** `unittest discover -s tests` **604 tests OK**; `scripts/check_project.py` PASS (28 documents). MOCK/STATIC only.
