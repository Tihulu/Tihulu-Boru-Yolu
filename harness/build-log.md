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

---

### 2026-11-22 — property-style hostile-input tests added (commit on `p1/boru-core-vertical-slice`)

- **Method:** beyond example-based tests, random bytes and text (control characters, bidi overrides, zero-width characters, oversized strings) are fed through the real broker/executor/consent/connector/contract paths with a deterministic seed. The exploratory run used 3000 rounds per property (~18,000 hostile inputs): **0 unhandled exceptions, 0 receipts verified without the key, 0 probes disclosing the resource path or entry names**; 497 well-formed names were accepted and 2,503 inputs were typed denials.
- **New coverage:** `tests/test_property_hostile_inputs.py` (5 properties, CI-sized at 250 rounds each) — random targets, aliases, forged receipts, connector payloads and typed results must each yield a typed outcome.
- **Tests observed:** `unittest discover -s tests` **609 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — auth slice self-review: four defects closed (commit on `p1/boru-core-vertical-slice`)

- **Duplicate `__post_init__`** in `OAuthClientConfig`: the second definition shadowed the first; defined once now, with a source check that fails if a second appears.
- **Unbounded attempt registry**: `OAuthFlow.start()` accumulated attempts forever; the registry is bounded (8 newest, finished attempts dropped first) so a long-lived flow object cannot grow without limit.
- **Nonce claim vs code**: the module claimed "state and nonce verification" while only `state` is verified (nonce verification needs a parsed, signature-checked ID token, which this slice does not implement). The docstring now states the limitation and the handle record it, instead of implying a check that does not exist.
- **Unbounded token metadata and expiry**: `TokenVault.register()` accepted any provider/account/scope length and any `expires_at` — including NaN or infinite, which no comparison can ever call expired and which `json.dump` writes as invalid strict JSON. Metadata is now bounded, the expiry must be finite, positive and within a ten-year horizon (validated on load as well as on register), and `exchange()` refuses a non-finite `expires_in` before recording a handle.
- **Tests observed:** `unittest discover -s tests` **613 tests OK** (new: 4 hardening tests in `tests/test_oauth.py`). MOCK/STATIC only.

---

### 2026-11-22 — cloud transport self-review: untyped crash closed (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** the cloud transport reuses `JanProvider`'s shared parser through `__new__` without running its constructor, and `_parse_reply` reads `self.model_response_is_path` when the reply names a different model. A mismatched-model reply therefore raised an untyped `AttributeError` instead of `ProviderFailure("invalid_response")` — a crash on the very path Gate 2 exercises. The shared attributes now have class-level defaults, the two reuse sites set them explicitly, and `CloudProvider.chat` validates `max_tokens` and `timeout` like the Jan transport.
- **New coverage:** `tests/test_cloud_provider.py` (`CloudParseSafetyTests`: mismatched model, six hostile bodies, bounded request parameters) — 3 tests, 616 total.
- **Tests observed:** `unittest discover -s tests` **616 tests OK**. MOCK/STATIC only.

---

### 2026-11-22 — dispatch declarations wired end to end (commit on `p1/boru-core-vertical-slice`)

- **Gap found by self-review:** `boru/connectors/workflows.py` claimed a dispatch is "validated against that declaration before any dispatch call", but `validate_dispatch_inputs` had no caller on the dispatch path — only the bounded-shape checks ran.
- **Wiring:** a `Grant` may now carry an owner-declared input schema (`input_declaration_json`, bounded to 16 KiB / 16 typed specs, validated at construction), `Grant.declared_inputs()` parses it, and `check_dispatch_body` validates the body's inputs against it before any transport. The declaration is owner-provided only: a dispatch body's extra top-level keys are now refused, so a payload can neither carry its own schema nor smuggle an extra key toward the endpoint.
- **Documentation corrected:** the workflows module no longer claims a file-reading schema step it does not perform; closing that last step (read the workflow file, then dispatch) is recorded as a pilot-gate task.
- **Tests observed:** `unittest discover -s tests` **618 tests OK** (2 new tests in `tests/test_connector_scope.py`). MOCK/STATIC only.

---

### 2026-11-22 — resource profiles: PERFORMANCE / BALANCED / RESOURCE_OPTIMIZED / CUSTOM (commit on `p1/boru-core-vertical-slice`)

- **Why:** the owner asked for modes that keep an idle host free of RAM/VRAM/swap pressure, modes that do not disturb active use, both GPUs usable when needed, and an optional way to keep models open in the background.
- **What was built:** `boru/resources.py` — four resource profiles (a performance knob, never an authorization axis) setting `max_agents`, `max_large_local_models`, `idle_eviction_seconds`, `keep_warm` and owner-declared device budgets. `RESOURCE_OPTIMIZED` releases a kept-warm model lease after 60 s idle; `PERFORMANCE` holds up to two large local models warm and never evicts; `CUSTOM` takes owner bounds (either evict idle or keep warm). Host RAM is read from `/proc/meminfo` where available; VRAM stays an owner-declared budget, never a guessed measurement.
- **Usage-safe idle eviction:** `LeaseLedger` stamps every lease; an agent lease is always released when the task ends and an in-flight task is never idle, so only a *kept-warm model lease* can be evicted, and only after the profile's own threshold.
- **The model-release boundary, stated honestly:** Boru releases its own lease and then asks the provider (`ChatProvider.unload`, new typed hook) to release the model. A provider with no documented lifecycle endpoint refuses with `unsupported_capability` (Jan today; the HOLD recorded in `docs/ROUTING_AND_RESOURCES.md`), and that refusal is recorded in the ledger rather than hidden.
- **Wiring:** `CoreConfig.resource_mode`/`resource_overrides`, `BoruCore` builds the profile and the scheduler from it, `boru resources` reports profile + lease bounds + detected RAM, `boru doctor` gained a memory check, and the docs record the mode table and the keep-warm/eviction semantics.
- **Tests observed:** `unittest discover -s tests` **635 tests OK** (new `tests/test_resources.py`, 10 tests, plus scheduler/core wiring tests). MOCK/STATIC only.

---

### 2026-11-22 — "repository text is English" is now enforced, not just stated (commit on `p1/boru-core-vertical-slice`)

- **Audit performed:** every tracked file was scanned for non-English letters. The only hits are `boru/i18n.py` (12 lines — the TR/EN/DE dashboard label table) and `tests/test_dashboard.py` (4 lines asserting those labels render), i.e. the user-facing localization AGENTS.md explicitly keeps in product scope. Commit messages, source comments, docs, harness, tests, scripts and examples are English.
- **Enforcement added:** the predicate lives in `boru.i18n` (`is_repository_english`, codepoint-based so the checking file itself stays English), `scripts/check_project.py` scans every tracked file against it, and `tests/test_repository_language.py` runs the same rule inside CI.
- **Tests observed:** `unittest discover -s tests` full suite with the new test; `scripts/check_project.py` PASS.

---

### 2026-11-22 — swap reporting, and the English rule made git-optional (commit on `p1/boru-core-vertical-slice`)

- **`boru resources` and `boru doctor` now report swap** (total/free from `/proc/meminfo`): the owner asked for an idle host free of RAM/VRAM/swap pressure, so swap belongs in the same report as RAM. Swap is reported, never tuned: swapping behaviour is the host's configuration and Boru only shrinks its own footprint by releasing leases.
- **Two defects found by the doctor's own suite run and fixed:** (a) the English-text rule flagged its own test file, because the file carried literal Turkish sample strings — the samples are built from code points now, so the file itself stays English while still proving detection; (b) the rule and its test required `git ls-files`, so an unpacked source tree (the evidence script's copied run) reported a failure — the file iterator now walks the tree when git is unavailable, with the same exemptions.
- **Tests observed:** `unittest discover -s tests` **639 tests OK**; `scripts/evidence.py` all checks PASS (static manifest, 639 unit tests, offline demo, install/uninstall round trip); `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — resource observability and a warm-lease bound defect fixed (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** the kept-warm record bound was enforced *before* insertion, so a `keep_warm` profile could hold `MAX_WARM_MODELS + 1` records; worse, a record dropped beyond the bound lost its lease mapping, leaving a model lease that no eviction could reach - exactly the "idle holds the device" problem the resource modes exist to prevent. The bound now applies at insertion and a displaced record always releases its lease (recorded as `warm_lease_displaced`).
- **Observability:** `boru resources --state-dir <dir>` now also reports what this process holds (agent / large-model / remote-call leases and the kept-warm model records) after releasing idle leases, and `status()` releases idle kept-warm leases before reporting, so a status report is an observation point rather than a stale snapshot. No device contents are ever read.
- **Tests observed:** `unittest discover -s tests` **641 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — store self-review: attempt records are objects, reads never crash (commit on `p1/boru-core-vertical-slice`)

- **Self-review of `boru/store.py`:** the durable-state store is well hardened (owner-only state directory, 0600 files, symlink and hard-link refusal, single-writer `flock`, compare-and-set transitions, bounded payloads, idempotency fingerprints); two gaps remained.
- **Gaps closed:** `save_result` accepted any JSON-serialisable value, so a non-object record could be stored and every later read of that attempt (for example `result_text`) would raise an untyped `AttributeError`; stored results must now be JSON objects, and the read path tolerates a hostile row (written by another writer or an older build) by reporting "no text" instead of crashing.
- **Tests observed:** `unittest discover -s tests` **643 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — budget self-review: reservations are bounded and released (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** `BudgetLedger` accumulated one reservation per dispatched task and never dropped or released it, so a long-lived process (a plan of many tasks, or repeated runs in one process) grew its reservation map without bound. Reservations are now bounded (newest kept, a stale record refused rather than remembered) and explicitly released when a task's life ends - at `review()` and `cancel()`, where no further usage is recorded.
- **Self-review of `boru/budgets.py` otherwise:** the honest-estimate and check-before/after rules hold; ceilings are validated at both ends, usage values must be non-negative integers, an unbounded cost ceiling is still refused before dispatch, and compaction is a documented deterministic bound, not a semantic summary.
- **Tests observed:** `unittest discover -s tests` **646 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — registry self-review: a health change no longer erases ranking metadata (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** `ModelRegistry.mark_health` rebuilt the record without `cost_tier`/`quality_tier`, so any transient failure (a rate limit, a timeout, a missing provider) silently replaced owner-declared ranking hints with `UNKNOWN` for the rest of the process - and an unknown cost is a *penalty* in the router, so one 429 quietly changed every later routing decision for that model.
- **Also fixed:** `mark_tested` raised an untyped `KeyError` for an unknown record, while `mark_health` raised a typed error; both are typed now, and `mark_health` validates the health state and the bounded error kind before writing.
- **Self-review of `boru/registry.py` otherwise:** provenance (`discovered`/`configured`/`verified`), health states, all-tags matching, `LOCAL_ONLY` filtering and the literal `UNKNOWN` for unobservable values are all preserved and unchanged.
- **Tests observed:** `unittest discover -s tests` **649 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — dashboard self-review: a local owner surface is still a surface (commit on `p1/boru-core-vertical-slice`)

- **Self-review of `boru/dashboard.py`** found five gaps in the loopback status page, all closed:
  1. an unbounded `Content-Length` read on `/review` - a malformed header raised an **untyped** error inside a network handler, and a huge one was read into memory before parsing; the body is now bounded (64 KiB) and a malformed length is a typed 400;
  2. an unvalidated `/task/<id>` path segment - an oversized id reached the store and raised an **untyped** error; the segment is bounded and single-segment, and the store's configuration error maps to a 400;
  3. no restrictive response headers - the self-contained page now carries a strict `Content-Security-Policy` and `nosniff`;
  4. unbounded connection threads - the surface now bounds concurrent connections and refuses past the bound with a typed 503 (draining the request first, so a client reads the refusal instead of a connection reset, and setting the request attributes the response writer needs before `parse_request` ran);
  5. a duplicated line in the render path.
- **Tests observed:** `unittest discover -s tests` **653 tests OK** (4 new hardening tests in `tests/test_dashboard.py`); `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — queue self-review: dispatch never fails for a bookkeeping limit (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** when the in-process replay history reached its bound, `BoundedTaskQueue.pop()` raised `QueueFull` — *after* removing the envelope from the queue, so dispatch lost the task and stopped working. The bound is now a documented sliding window: a consumed key leaves the window oldest-first, and the module records that `TaskStore.submit`'s idempotency fingerprint is the authoritative replay guard while this window covers the in-process case. A pop never raises for bookkeeping and never loses an item; `put()` still refuses a duplicate key inside the window.
- **Self-review of `boru/state.py`:** the transition table is complete and terminal for `DONE`/`CANCELLED`; `HOLD` resumes into the pipeline; an agent's self-report can never reach `DONE` (only the owner review path promotes it, from `REVIEW`). No change needed.
- **Tests observed:** `unittest discover -s tests` **654 tests OK** (new: bounded-window test in `tests/test_queue.py`); `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — CLI self-review: a bad state directory is reported, not ignored (commit on `p1/boru-core-vertical-slice`)

- **Self-review of the CLI surface** with deliberately bad input (missing file, invalid JSON, invalid config, a state directory that is a file, a non-numeric audit limit, an oversized task id): every path produced a typed error with a stable `kind` and no traceback - except `boru resources --state-dir <file>`, which silently reported an empty lease view. The lease view is now a reported failure, so an unusable state directory cannot look like "nothing is held".
- **Also reviewed in this pass:** `boru/state.py` (complete transitions, terminal states, no agent self-report path to `DONE`) and `boru/queue.py` (fixed in the previous entry).
- **Tests observed:** `unittest discover -s tests` **654 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — connect self-review: a bounded authorization wait and scope list (commit on `p1/boru-core-vertical-slice`)

- **Self-review of `boru/connect.py` and the scope helper:** the owner-run OAuth/PKCE flow accepted `--timeout` values of any size, so one typo could make a command wait for days (a bound that is not a bound), and the scope list was bounded per value but not in count, so an unbounded `--scope` repetition would turn the authorization URL into a weapon-sized request. The authorization wait is now bounded 1..3600 seconds (a typed refusal outside it) and at most 16 scopes may be requested.
- **Everything else in this module reviewed and unchanged:** the loopback-only redirect, the single captured response, state verification, the opaque-handle-only vault write, and the honest `authenticated` state that is never reported as inference authorization.
- **Tests observed:** `unittest discover -s tests` **654 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — install/uninstall self-review: the launcher works anywhere and the uninstaller refuses harm (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed (installer):** the generated launcher ran `exec python3 -m boru` with no `PYTHONPATH`, so the installed command only worked when the owner's working directory happened to contain the copied `boru/` tree. The launcher now puts the install directory on `PYTHONPATH`, and the installer resolves `--target`/`--state-dir`/`--bin-dir` to absolute paths first, so a relative flag cannot bake a relative path into the launcher.
- **Defect found and fixed (installer):** a re-install merged into the existing tree, so a module removed upstream could survive as a stale import. The installer now replaces Boru's own tree (Boru-owned paths only) before copying.
- **Safety hardening (uninstaller):** a destructive `rm -rf` now refuses a target or state directory that is empty, relative, a root, a home path or a system directory (`/`, `$HOME`, `/bin`, `/etc`, ...) with exit 2 and nothing removed; only Boru-owned absolute paths are considered, and an unrelated command in the same `--bin-dir` survives.
- **Tests observed:** `unittest discover -s tests` **663 tests OK** (4 new tests: launcher from an unrelated directory with an absolute path, re-install replacement, dangerous-target refusals, unrelated-command survival); `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — the install evidence now exercises the launcher (commit on `p1/boru-core-vertical-slice`)

- **Change:** `scripts/evidence.py` ran the installed demo as `python -m boru demo` with the working directory set to the copied tree, which is the path a missing `PYTHONPATH` would NOT break. The round trip now runs the **installed launcher from an unrelated working directory** — the path an owner actually uses after install, and the path the previous entry's defect would have broken.
- **Tests observed:** `scripts/evidence.py` all checks PASS (static manifest, 663 unit tests, offline demo, install/demo/uninstall round trip); `unittest discover -s tests` **663 tests OK**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — doctor precedence and the last two modules reviewed (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed:** `boru doctor` computed its overall verdict so a `hold` masked a `fail`, so a broken state directory read as `hold` and an acceptance run could miss it. Precedence is now fail > hold > ok.
- **Self-review of the last two unreviewed files:** `boru/doctor.py` (checks are read-only, bounded timeouts, no host state beyond what the checks name, a `hold` for a platform that reports no memory) and `boru/i18n.py` (fixed owner-visible labels only; the English-repository predicate is codepoint-based so the checking file stays English). No other change needed.
- **Tests observed:** `unittest discover -s tests` **665 tests OK (1 skipped)**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — second-pass self-review: a blocking special file could hang the worker (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed (confirmed by reproduction, not by reading):** `LocalExecutor._open_target` opened a target with `O_RDONLY|O_NOFOLLOW` and no `O_NONBLOCK`, so a FIFO (or another blocking special file) placed inside a declared resource **blocked the worker indefinitely** — a directory entry any owner-level writer could create, with no typed outcome and no timeout. The target open now adds `O_NONBLOCK`, which has no effect on regular file reads.
- **Behaviour after the fix:** a FIFO probe answers immediately with `{"exists": true, "type": "other", "size": null}`, and reading it is refused because it is not a regular file.
- **Why this one survived the first pass:** the first pass asked "can a target escape the alias?" (traversal, symlinks, `..`); this one asks "can a target stop the worker?" — a different question class, found by executing rather than reading.
- **Tests observed:** `unittest discover -s tests` **666 tests OK (1 skipped)**; the new regression test bounds the acquisition to 5 seconds so a regression fails instead of hanging the suite. `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — second-pass self-review: an envelope payload was unbounded (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed (confirmed by execution):** `TaskEnvelope.validate()` did not bound its `payload` at all, so a 20 MB `messages` entry passed the typed contract and reached `TaskStore.submit`. The result contract had been bounded recursively since F10; the request contract had not, and the asymmetry was the defect. `TaskEnvelope` now validates its payload: only a bounded message list, bounded roles and content, no other keys.
- **Also verified in this pass:** `RejectionLedger.recent` is bounded (1..1024) and refuses a negative limit; `BoruCore.submit` calls `assert_valid()` before the durable store, so the production path is now protected at the contract boundary rather than at the storage boundary.
- **Tests observed:** `unittest discover -s tests` **669 tests OK (1 skipped)**; the new tests cover seven hostile payload shapes, three well-formed ones and the core submission path. `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — second-pass self-review: a task's event history is a bounded window (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed (confirmed by execution):** the durable `events` table had no per-task bound and `_get` loaded every event for a task. `HOLD`/`CLASSIFIED` cycles are legal and repeatable, so a long-lived process cycling one task grew that table and every read of it without end (30k events = 3.3 MB of JSON per task read, and the dashboard reads every task).
- **Fix, in the repository's established pattern:** the newest bounded window of one task's transitions is kept (the task's *state* is authoritative, not its history), and a read is bounded even for rows written by an older build.
- **Second-pass findings so far:** a blocking special file could hang the worker (fixed with `O_NONBLOCK`), an envelope payload was unbounded (fixed with a bounded message contract), and now the event window. Reading alone did not surface any of the three; each was found by executing an input the author had not imagined.
- **Tests observed:** `unittest discover -s tests` **671 tests OK (1 skipped)**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — second-pass self-review: a configuration is bounded work too (commit on `p1/boru-core-vertical-slice`)

- **Defect found and fixed (confirmed by execution):** `CoreConfig.validate()` accepted an unbounded provider and classification list (5000 providers validated with zero errors). Boru Core never accepts unbounded work, including from its own configuration: at most 32 providers and 64 declared outbound directions are accepted.
- **Second-pass findings, fourth in this pass:** a blocking special file could hang the worker; an envelope payload was unbounded; a task's event history was unbounded; and now the configuration itself. Reading alone did not surface any of them.
- **Tests observed:** `unittest discover -s tests` **673 tests OK (1 skipped)**; `scripts/check_project.py` PASS. MOCK/STATIC only.

---

### 2026-11-22 — branch pushed with owner authorization through the local agent (head `988738a` on `p1/boru-core-vertical-slice`)

- **Push executed by the authorized local agent** (`jan-local/Qwen3_6-35B-A3B-UD-IQ4_XS`) under the owner's session authorization: `git push origin p1/boru-core-vertical-slice` → `cc73940..988738a`, 43 commits, remote head `988738a`. Working tree clean before and after; no files modified.
- **CI:** run `#45048886502` ("Source-only contract checks") was triggered for this head; its outcome is recorded below once the local agent reports it — the package is not linked to a run whose result is unknown.
- **Routing note recorded honestly:** the cloud coordinator did not execute host Shell directly for the push; the operation ran through the independently authorized local agent, and only a sanitized report (SHA, run id, tree state) crossed back.

---

### 2026-11-22 — CI green on the pushed head; Gate 1 package re-pinned (commit on `p1/boru-core-vertical-slice`)

- **CI verified:** run `#45048886502` on head `988738a` concluded **success** (no failed jobs or steps), reported by the authorized local agent. Link: https://github.com/Tihulu/Tihulu-Boru-Yolu/actions/runs/45048886502
- **Package re-pinned:** `docs/REVIEW_PACKAGE.md` now cites this head's own CI run instead of the previous head's, and no longer states that a run is pending.
- **Gate 1 state:** the remediation work, the local verification (673 tests, 20/20 probes, check/evidence/doctor) and the CI run are all in place; what remains is the **independent verdict**, which belongs to the reviewer.

---

### 2026-11-22 — CI green on the final head; Gate 1 fully prepared (head `e9854a6` on `p1/boru-core-vertical-slice`)

- **CI verified:** run `#45051589592` on head `e9854a644c9ebfdddd3909d6e0ba579b993c338b` concluded **success** (job `validate`, no failed steps), reported by the authorized local agent. Remote head confirmed as `e9854a644...`.
- **Combined Gate 1 evidence on this head:** 673 tests OK locally, the reviewer's 20 probes passing inside CI's suite, `check_project.py`/`evidence.py`/`boru doctor` all green locally, and two consecutive green CI runs (45048886502, 45051589592).
- **Remaining for Gate 1:** the independent verdict, which belongs to the reviewer; the request is ready in `docs/RE_REVIEW_REQUEST.md`.

---

### 2026-11-22 — Gate 2 preparation: --dry-run validates the five registration values (commit on `p1/boru-core-vertical-slice`)

- **Why:** Gate 2 is blocked on the owner's provider registration, so everything that can be done *before* it was done. A wrong endpoint, a non-loopback redirect or a busy port would otherwise be discovered only after the owner has spent a registration.
- **What was added:** `boru connect --dry-run` validates what can be validated without contacting the provider — both endpoints https, redirect numeric loopback with a port bindable on this host *right now*, scopes within the 16 bound, vault directory usable and owner-only — and prints the authorization URL that would be opened. A refusal is typed (`configuration_error` for a bad value, `not_ready` for this host) and names what to fix; nothing is sent anywhere.
- **Documentation:** `docs/AI_PROVIDER_CONNECTIONS.md` now names the five values a registration must bring back, states that a provider refusing a plain-HTTP loopback redirect is a documented limitation rather than a bypass, and documents the dry-run pre-flight.
- **Tests observed:** `unittest discover -s tests` **676 tests OK (1 skipped)**; the new tests cover the ready path, four refusal classes and a busy redirect port. `scripts/check_project.py` PASS. MOCK/STATIC only — no provider was contacted.

---

### 2026-11-22 — SESSION HANDOFF (restart) — resume here

**Branch:** `p1/boru-core-vertical-slice` (draft PR #14, not merged). Base branch:
`plan/architecture-security-profiles-ubuntu-popos` (draft PR #1), not `main`.

**Head at handoff:** `02ce191` — "docs(review): name the pushed CI-green head in the
re-review request". Working tree clean; pushed (remote head `02ce191`); CI green on
this head and on every pushed head before it (runs 45048886502, 45051589592,
45054735298, 45056795448, 45059854129 — all `success`).

**Verified state at handoff (all re-run on this head):**
- `python3 -m unittest discover -s tests` → **676 tests OK (1 skipped)**
- `PYTHONPATH=. python3 tests/test_review_regressions.py` → **20/20 OK** (the Gate 1
  reviewer's own probes, now inside the suite)
- `python3 scripts/check_project.py` → PASS (30 required documents + policy invariants)
- `python3 scripts/evidence.py` → exit 0 (static manifest, 676 unit tests, offline
  demo, install → demo → uninstall round trip — the demo now runs through the
  installed launcher from an unrelated directory)
- `python3 -m boru.cli doctor` → overall ok / `live_acceptance: HOLD`
- Live evidence from earlier gates: A21 (direct Jan, 3 conversations), A23 (real
  OpenCode child session). No cloud inference has occurred.

**Completed this session:** Gate 1 remediation (F01–F22 per
`docs/REVIEW_FINDINGS.md`, with F06/F20 explicitly marked *to re-confirm* because
their canonical text is not in the working notes); a second adversarial self-review
pass that found and fixed four more defects (a blocking special file could hang the
worker; an envelope payload was unbounded; a task's event history was unbounded; a
configuration's provider/classification lists were unbounded) plus the earlier
campaign's ~30; the four resource profiles (PERFORMANCE/BALANCED/
RESOURCE_OPTIMIZED/CUSTOM) with usage-safe idle eviction, keep-warm and
`boru resources`; the English-repository rule enforced in CI; the Gate 1 package
re-pinned to this head's own green CI run; and the Gate 2 pre-flight
(`boru connect --dry-run`, the five registration values in
`docs/AI_PROVIDER_CONNECTIONS.md`).

**Where we stopped — the exact next action (owner's step, then the agent's):**
1. **A (Gate 1):** the owner is to paste the ready-to-send re-review request
   (`docs/RE_REVIEW_REQUEST.md`, and the identical text given verbatim in chat) to
   the external reviewer. The owner then pastes the reviewer's reply back. The
   agent's next action on that reply: remediate each new finding with a regression
   test, commit, push (through the authorized local agent) and wait for CI; test the
   canonical F06/F20 text when it arrives and close those rows; on a clean verdict,
   record Gate 1 as passed in this ledger.
2. **B (Gate 2):** the owner names the provider (OpenAI / Anthropic / GitHub /
   GitLab). The agent then writes the exact console steps, validates the five
   returned values with `boru connect --dry-run`, runs the real connection and
   records the opaque-handle + `identity_is_not_inference: true` evidence.

**Operating notes for the next session:**
- Pushes are executed by the **authorized local agent** (`tihulu-qwen-local`) under
  the owner's session authorization, not by the cloud coordinator; each push is
  followed by a CI watch by the same agent.
- The repository text is English and this is enforced by
  `tests/test_repository_language.py` and `scripts/check_project.py`; the user-facing
  dashboard localization (`boru/i18n.py` + its test) is the only exemption.
- Do not weaken while remediating: LOCAL_ONLY / LOCAL_ISOLATED / MINIMUM_NECESSARY
  defaults and the four independent policy axes; a resource profile never widens a
  policy bound; a provider identity is never an inference entitlement.
- Release gates still requiring owner action: provider OAuth registration, a
  disposable repository for the connector pilot, clean-machine Pop!_OS/Ubuntu
  M01–M12, and license + release approval (`docs/OWNER_GATE_GUIDE.md`).

---

### 2026-11-23 — Gate 3 preparation: the connector pilot runbook and script (commit on `p1/boru-core-vertical-slice`)

- **Why:** Gate 3 needs an owner-created disposable repository, so everything that can be done *before* that was done. The pilot was a plan, not a procedure.
- **What was built:** `scripts/connector_pilot.py` — one command that runs the four grant-bound denials, then the read pilot, the write pilot (draft PR only) and the Actions pilot, emitting a sanitized evidence block (object IDs, decisions, denial reasons — never a token, a path or a private payload). `--dry-run` makes no outbound request at all: the transport refuses any exchange, so the claim is enforced by construction.
- **Defect found and fixed while building it:** the first draft's dry-run actually reached the network (a dummy credential produced a real `identity_endpoint_refused` from GitHub) and two of the "denial" cases were mis-constructed — the payload matched the grant, so the binding check passed. The denials now name the pilot repository in the grant and another in the payload, producing `repository_not_granted`, `reference_not_granted`, `operation_not_granted` and `workflow_required`, and the dry-run's refusing transport makes the no-network claim true.
- **Tests observed:** `unittest discover -s tests` **680 tests OK (1 skipped)**; the new tests cover the no-credential refusal, the malformed repository, the four denial reasons and the checkout-relative import. `scripts/check_project.py` PASS. MOCK/STATIC only — no provider was contacted.

---

### 2026-11-23 — Gate 4 preparation: the M09 listener proof is now mechanical (commit on `p1/boru-core-vertical-slice`)

- **Why:** Gate 4 runs on clean images the owner provides; its mechanical checks should be one command each so an image is proved, not narrated.
- **What was built:** `scripts/listener_check.py` — starts the loopback dashboard, verifies the address it actually bound is a numeric loopback address, verifies a public bind is refused by construction, stops it and verifies the port is released and no thread survives the stop (the live thread count returns to the pre-start count). The report carries an address class and a port number, never a path, a token or a host inventory.
- **Defect found while building it:** the thread check first counted threads by name, which is always zero with the default `Thread-N` naming — a vacuous proof. It now compares the live thread count before start and after stop, which is a real criterion (1 before, 1 after: the main thread).
- **Tests observed:** `unittest discover -s tests` **681 tests OK (1 skipped)**; the new test asserts each M09 criterion and that the report carries no path. `scripts/check_project.py` PASS. MOCK/STATIC only.
