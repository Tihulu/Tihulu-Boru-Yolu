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
