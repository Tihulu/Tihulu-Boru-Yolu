# Acceptance plan and evidence matrix

## Evidence classes

- **PASS:** reproducible test run or direct inspected evidence.
- **FAIL:** observed negative result.
- **HOLD:** unexecuted, blocked or unknown.
- **DESIGNED:** architectural intent only; **not** a PASS.
- Avoid self-reported "I invoked Qwen" without child-session/provider evidence.
- Report executed test counts (not source count) and include test command, host OS release *without private inventory*, tool versions and sanitized failure categories.

## Acceptance cases

| ID | Target | Expected result | Current |
| --- | --- | --- | --- |
| A01 | Pop!_OS isolated install | No changes to Jan/OpenCode live state | HOLD |
| A02 | Ubuntu LTS isolated install | No changes to Jan/OpenCode live state | HOLD |
| A03 | Kandev bind / authentication exposure | Loopback only for pilot, no unintended remote listener | HOLD |
| A04 | Langflow local authentication | Login enabled, no anonymous API access | HOLD |
| A05 | Jan chat via Langflow | Correct actual local model, 3 turns | HOLD (direct Langflow path not exercised; A21 covers direct Jan) |
| A06 | OpenCode subagent via Kandev | Verified child session and model, not skill fallback | HOLD |
| A07 | Kandev -> adapter -> Langflow | One task, one flow, correct status | HOLD |
| A08 | AUTO vs ECONOMY vs PERFORMANCE | Observable policy-dependent selection | HOLD |
| A09 | LOCAL_ONLY no cloud | Zero provider requests on all failure paths | HOLD |
| A10 | Token/rate-limit fallback | Bounded retries, no policy escalation | STATIC PASS (MOCK): reservation + observed-usage recheck, cooldown, bounded fallback; LIVE HOLD |
| A11 | Local Shell only | Cloud cannot bypass local broker | STATIC PASS (MOCK): allowlist/alias/scope/replay/expiry/revocation all deny; executor and OS isolation still HOLD |
| A12 | Cloud Shell opt-in | Sandbox + live scoped grant required | HOLD |
| A13 | Cloud Shell revocation | Stops pending jobs and prohibits new ones | HOLD |
| A14 | Privacy Bridge | Typed minimal disclosure; no raw stdout | STATIC PASS (MOCK): gate + broker + bounded worker refuse content/listings/raw fields; live disclosure path HOLD |
| A15 | Protected extra data | Exact recipient/field approval before disclosure | STATIC PASS (MOCK): L2 refused under MINIMUM_NECESSARY, field-level denial, recipient-bound consent; live HOLD |
| A16 | Adversarial inputs | Prompt-injection, replay, schema overflow denied | STATIC PASS (MOCK): policy axes, grant replay/expiry/revocation, malformed contracts, private-field refusal, off-trajectory paths not introduced |
| A17 | Resource lifecycle | Owned models only, cancel/unload no leaks | STATIC PASS (MOCK): leases are counted and only Boru-owned leases are released; live OS measurements HOLD |
| A18 | Up to 6 logical agents | Resource limits, evidence per child | HOLD |
| A19 | Rollback | Jan/OpenCode unchanged and launchable | HOLD |
| A31 | Provider capability/auth matrix and secret-free example | English matrix in docs/AI_PROVIDER_CONNECTIONS.md | STATIC PASS (documentation); no account connected |
| A20 | Static repo consistency | `scripts/check_project.py` + unittest | STATIC PASS (669 tests on the P1-P10 source slices, MOCK only) |
| A30 | Install/rollback round trip | user-space install → demo → uninstall, only Boru-owned paths removed | STATIC PASS (script round trip, not a clean-machine matrix) |
| A21 | Boru Core independence | Runs direct Jan text-only flow without TIHULU-AUTO installed | LIVE PASS (3 x 3-turn conversations, direct evidence, allowlist refusal verified) |
| A22 | OpenCode and Jan standalone | Existing app/API and sessions function with Boru Yolu and TIHULU-AUTO stopped | HOLD |
| A23 | Optional OpenCode agent adapter | Real child invocation without any TIHULU-AUTO config or agent; disabling adapter is non-disruptive | LIVE PASS for the child-session evidence (official CLI, disposable directory, sessions deleted); adapter live integration HOLD pending owner-authorized auth material |
| A24 | Optimization policy isolation | AUTO/ECONOMY/BALANCED/PERFORMANCE/MANUAL never change Shell, disclosure or inference rights | HOLD |
| A25 | Local-only under provider failure | LOCAL_ONLY blocks remote inference and fallback on 429, timeout and missing model | HOLD |
| A26 | Privacy Bridge failure | No raw stdout, private source or unfiltered output leaves local boundary on success/failure | STATIC PASS (MOCK): local pipeline denies on every failure path and returns typed fields only; live boundary HOLD |
| A27 | Cloud Shell grant isolation | Explicit, scoped, revocable, sandbox-only grants cannot become host Shell | HOLD |
| A28 | Data disclosure and model fallback | New provider recipient requires matching disclosure consent; no silent additional data | HOLD |
| A29 | Economy/performance and six agents | Measured token budgets, bounded concurrency and memory leases without extra privilege | HOLD |

## Test matrix by OS

| Distribution | Native Kandev | Langflow venv | Jan local API | OpenCode adapter | Sandbox | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| Pop!_OS 24.04 x86_64 | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |
| Ubuntu 24.04 LTS x86_64 | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |
| New supported Ubuntu LTS (version pinned later) | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |

Clean-machine matrix (M01–M12) and rollback checklist: `docs/OS_ACCEPTANCE.md`, all rows HOLD until an owner runs them.

Do not infer Linux compatibility solely from a product's marketing page. Test exact binaries on the supported target image.

`python3 scripts/evidence.py` produces the sanitized evidence block for this
machine (commit, Python version, platform, check statuses, `live_acceptance:
HOLD`, MOCK/STATIC note). It is reproducibility tooling, not an acceptance
substitute: live gates still require the owner's approved runs.

## Two critical demonstrations

### Default local-isolated

Ask cloud coordinator for an authorized local project existence check. Only an authenticated local worker runs it, returns typed `{"exists":true}` through Privacy Bridge, and the cloud sees no unrelated paths/logs. If local worker is down, cloud receives `HOLD`, not direct host Shell.

### Owner-opted cloud Shell

User explicitly selects CLOUD_SHELL_APPROVAL, approves a one-off synthetic read-only operation inside an isolated demo sandbox, and verifies exact capability, expiration, recipient, output filter and audit. Same request without approval, outside sandbox or after revocation must be denied. There must be no way to switch from this mode to arbitrary host execution through model instructions.

## CI vs production

Repository CI can check JSON contract and static docs with no secrets. It **cannot** verify host isolation, cloud privacy, actual GPU/memory unloading, consent UI or plugin permissions. These require controlled platform acceptance.
