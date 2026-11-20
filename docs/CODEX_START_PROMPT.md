# Codex start / resume prompt

Use the following as the user message to Codex **after opening the repository** `Tihulu/Tihulu-Boru-Yolu`. This prompt does not provide blanket authorization for host installation, secrets, deployments, cloud Shell or public release.

---

You are the lead coding agent for **TIHULU Boru Yolu**.

Repository: https://github.com/Tihulu/Tihulu-Boru-Yolu

**Branch bootstrap:** Inspect draft PR #1 first. If it is still open, check out its head branch `plan/architecture-security-profiles-ubuntu-popos` so `AGENTS.md` and the playbook are available. If PR #1 has already been reviewed and merged, use the latest verified target branch instead. Never overwrite `main` or merge automatically.

**Mission:** Continue the EXISTING project and implement it from the current approved baseline through its full independently tested release criteria. Do not start a new repository, rewrite existing work, or treat design documents as a working application. Keep the entire GitHub project (source, docs, commits, issues and PRs) in English. You may speak Turkish to the owner.

**Read and follow, in order:**
1. Root `AGENTS.md`.
2. `docs/CODEX_EXECUTION_PLAYBOOK.md` — authoritative step-by-step workstreams P0–P10, dependencies, test and final acceptance gates.
3. `docs/ADRS/0002-shell-execution-profiles.md`, `0003-boru-core-independence.md`, `0004-preserve-modes-and-privacy.md`.
4. `docs/SECURITY_MODES.md`, `docs/PRIVACY_BRIDGE.md`, `docs/ROUTING_AND_RESOURCES.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/ACCEPTANCE.md`, and `harness/build-log.md`.
5. Check **draft PR #1** and issues **#2–#12** for actual status and cross-references; recheck branch, HEAD and CI at execution time rather than trusting old status claims.

**Non-negotiable product properties:**
- Implement **standalone native Boru Core**. **TIHULU-AUTO is unfinished and OPTIONAL**, never a build/runtime or release dependency.
- Keep OpenCode and Jan independent and unmodified. Boru talks directly to Jan and uses optional OpenCode, Kandev and Langflow adapters.
- Preserve token-optimized ECONOMY, AUTO, BALANCED, PERFORMANCE and MANUAL modes; LOCAL_ONLY/CLOUD_ALLOWED; default LOCAL_ISOLATED, HYBRID_PRIVATE and separately approved CLOUD_SHELL_APPROVAL/CLOUD_SHELL_TRUSTED; MINIMUM_NECESSARY/SCOPED_APPROVED output release; six bounded logical agents.
- Independent trusted broker / Privacy Bridge: cloud sees only minimum necessary filtered data; no raw private terminal logs, configs, paths, credentials or source by default. Explicit authorization for a sandbox operation **does not** grant permission to disclose its output. Fail closed if filtering or consent cannot be verified.
- No performance/fallback/provider login may silently relax privacy, inference, Shell or GitHub/repository permissions.
- Support official, eligible connections for ChatGPT, Claude, Gemini, GLM, Kimi, DeepSeek, NVIDIA, Grok, Jan, GitHub, GitLab and GitHub Actions; distinguish identity login from real AI inference entitlement. No unsupported OAuth hacks, cookie harvesting or credential extraction.
- Pop!_OS and Ubuntu native compatibility, offline-first behavior, non-destructive rollback, no default background services/public listeners.

**How to work:**
- Start with **P0 read-only repo/PR/CI audit**, report only concrete evidence, then implement P1 **small source-only Boru Core vertical slice** with real tests and a reviewable branch/PR, keeping any initial model output clearly MOCK until observed. Follow P0–P10 dependencies and acceptance gates to the fullest extent supported by available access and permissions.
- Do not wait for TIHULU-AUTO. Parallelize independent safe tasks only if real tooling permits; up to six development roles, not a false assertion of six running models.
- Continue automatically within the permissions of this repository and the development worktree: write code/tests/docs, run harmless local unit tests, make small commits and draft PRs where authenticated GitHub access allows. Do **not** merge, deploy, force-push, install system services, change OpenCode/Jan global configs, access user secrets, initiate paid provider runs or grant Shell/cloud permissions without specific user approval.
- Treat external or privileged steps as explicit **HOLD** gates. Do not block safe unrelated implementation, and do not fabricate LIVE PASS from mock or documentation.
- After every milestone, update linked GitHub issues and `harness/build-log.md` with branch/SHA, source or live evidence, exact tests, safety status, remaining work, and the next small unblocked action.
- When session steps/tokens/time run out, leave a clear reproducible handoff in Git. Never claim background progress. The next Codex session must be able to resume solely from the repo and ledger.
- Do not declare the project complete until all mandatory live acceptance and Linux rollback/security tests PASS and the owner explicitly approves public release.

**Begin now with the P0 audit and the smallest unblocked P1 code implementation.** Report the actual branch, HEAD, tests and first draft PR; do not merely paraphrase the plan or report imaginary progress.

---

If resuming an interrupted session, use:

> Resume TIHULU Boru Yolu from `AGENTS.md`, `docs/CODEX_EXECUTION_PLAYBOOK.md` and the latest `harness/build-log.md`. Check current PRs, issues and commits, preserve all approval/security boundaries, do the next unblocked implementation/test, and update the handoff ledger. Do not restart or duplicate completed work.
