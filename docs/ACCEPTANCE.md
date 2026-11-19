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
| A05 | Jan chat via Langflow | Correct actual local model, 3 turns | HOLD |
| A06 | OpenCode subagent via Kandev | Verified child session and model, not skill fallback | HOLD |
| A07 | Kandev -> adapter -> Langflow | One task, one flow, correct status | HOLD |
| A08 | AUTO vs ECONOMY vs PERFORMANCE | Observable policy-dependent selection | HOLD |
| A09 | LOCAL_ONLY no cloud | Zero provider requests on all failure paths | HOLD |
| A10 | Token/rate-limit fallback | Bounded retries, no policy escalation | HOLD |
| A11 | Local Shell only | Cloud cannot bypass local broker | HOLD |
| A12 | Cloud Shell opt-in | Sandbox + live scoped grant required | HOLD |
| A13 | Cloud Shell revocation | Stops pending jobs and prohibits new ones | HOLD |
| A14 | Privacy Bridge | Typed minimal disclosure; no raw stdout | HOLD |
| A15 | Protected extra data | Exact recipient/field approval before disclosure | HOLD |
| A16 | Adversarial inputs | Prompt-injection, replay, schema overflow denied | HOLD |
| A17 | Resource lifecycle | Owned models only, cancel/unload no leaks | HOLD |
| A18 | Up to 6 logical agents | Resource limits, evidence per child | HOLD |
| A19 | Rollback | Jan/OpenCode unchanged and launchable | HOLD |
| A20 | Static repo consistency | `scripts/check_project.py` + unittest | NOT RUN HERE |

## Test matrix by OS

| Distribution | Native Kandev | Langflow venv | Jan local API | OpenCode adapter | Sandbox | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| Pop!_OS 24.04 x86_64 | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |
| Ubuntu 24.04 LTS x86_64 | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |
| New supported Ubuntu LTS (version pinned later) | HOLD | HOLD | HOLD | HOLD | HOLD | HOLD |

Do not infer Linux compatibility solely from a product's marketing page. Test exact binaries on the supported target image.

## Two critical demonstrations

### Default local-isolated

Ask cloud coordinator for an authorized local project existence check. Only an authenticated local worker runs it, returns typed `{"exists":true}` through Privacy Bridge, and the cloud sees no unrelated paths/logs. If local worker is down, cloud receives `HOLD`, not direct host Shell.

### Owner-opted cloud Shell

User explicitly selects CLOUD_SHELL_APPROVAL, approves a one-off synthetic read-only operation inside an isolated demo sandbox, and verifies exact capability, expiration, recipient, output filter and audit. Same request without approval, outside sandbox or after revocation must be denied. There must be no way to switch from this mode to arbitrary host execution through model instructions.

## CI vs production

Repository CI can check JSON contract and static docs with no secrets. It **cannot** verify host isolation, cloud privacy, actual GPU/memory unloading, consent UI or plugin permissions. These require controlled platform acceptance.
