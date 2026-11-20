# TIHULU Boru Yolu — Codex / Coding Agent Instructions

> Scope: this repository only. These instructions are for agents developing Boru Yolu, not proof that the product's planned security restrictions are already implemented.

## Read first
1. `README.md` and `docs/ARCHITECTURE.md`.
2. `docs/ADRS/0003-boru-core-independence.md` and `docs/ADRS/0004-preserve-modes-and-privacy.md` (authoritative non-regression requirements).
3. `docs/SECURITY_MODES.md`, `docs/PRIVACY_BRIDGE.md`, `docs/ROUTING_AND_RESOURCES.md`.
4. `docs/CODEX_EXECUTION_PLAYBOOK.md` (master execution and stop/go gates), `docs/ACCEPTANCE.md`, and `docs/ROADMAP.md`.
5. `harness/build-log.md` for the current evidence-based state. Follow the earliest unfinished unblocked phase, not a self-reported percentage.
6. GitHub issues #2–#12; their scope may evolve; no issue being opened is evidence of implementation.

## Permanent architecture invariants
- Build **native independent Boru Core**, not a TIHULU-AUTO wrapper. TIHULU-AUTO is optional, disabled by default and never a prerequisite.
- **OpenCode** and **Jan** remain independently usable with Boru Yolu stopped, absent or uninstalled. Do not alter, terminate, replace or migrate their live sessions, providers, model weights or global configs.
- Boru Core can invoke a directly configured **Jan model without OpenCode, Kandev, Langflow or TIHULU-AUTO**. Optional adapters fail independently.
- Preserve four **independent axes**: optimization (`AUTO/ECONOMY/BALANCED/PERFORMANCE/MANUAL`), inference (`LOCAL_ONLY/CLOUD_ALLOWED`), execution (`LOCAL_ISOLATED/HYBRID_PRIVATE/CLOUD_SHELL_APPROVAL/CLOUD_SHELL_TRUSTED`) and disclosure (`MINIMUM_NECESSARY/SCOPED_APPROVED`).
- A model switch, performance preset, API login, repository connection or quota fallback **never grants** Shell access, remote inference rights, disclosure rights or GitHub write permissions.
- Default Shell is **local-only, authenticated and confined**. Cloud-controlled Shell is opt-in, **sandbox-only**, explicitly scoped, time-limited and revocable, with separate output disclosure consent. No unrestricted cloud-to-host shell in v1.
- **No raw private terminal output to cloud by default.** Trusted local filtering must run *before* remote delivery. Deny/HOLD on policy ambiguity or unavailable broker. No prompt-only authorization.
- Up to six *logical* agents, bounded by actual RAM/VRAM/rate/budget limits. Never assume six large local models can coexist or unload models used by unrelated sessions.
- Use officially supported authentication/API methods only. Login identity is not authorization for model inference or subscription billing. No cookie/token scraping from ChatGPT, Gemini, Claude, Codex or OpenCode.
- All GitHub repository documentation, source comments, test names, commit messages, issues and PR text must be **English**. Keep user-facing TR/EN/DE localization in product scope.

## Development authority and boundaries
- May inspect and modify **this repository's development branch/worktree** and run local, harmless build/unit tests in a disposable environment if tooling and permissions permit.
- Never treat access to the developer's Shell as production authorization; no commands against their actual Jan/OpenCode app or private filesystem without a separate authorized pilot.
- Do not merge or force-push, rewrite history, publish packages, deploy, change protected settings/secrets, install system services, run privileged commands or trigger costly CI on private/shared runners without explicit owner approval.
- Never enable public ports, background autostart, network egress or credential-bearing Actions by default.
- Keep provider OAuth tokens/API keys in an approved local secrets store; never commit, print, upload or embed them in agent prompts, logs or CI artifacts.
- Test GitHub/GitLab writes in **disposable repositories** with per-operation scope; never use an existing production repository as a test target.
- Source-only simulation and CI checks may validate interfaces but cannot prove live security, isolation, real OAuth, model calls or Linux platform support.
- Stop at gates requiring owner consent (host install, secret/account authorization, restricted CI, external billing, security sign-off, public release). Record HOLD with the exact next requested action. Continue other independent safe work.

## Implementation discipline
- Start by inspecting actual repo state: branch, PR, existing files, CI, current runtime. Do not assume app code or integrations exist just because docs or issues do.
- Prefer versioned, typed interfaces; explicit failure, cancellation, deadlines, idempotency keys and evidence provenance. Implement one thin vertical slice at a time.
- Do not replace existing tech stacks just to follow a new design. Propose an ADR before committing to major framework/architecture changes.
- Require real provider/model/child-session/run IDs for claiming integration success; never substitute fake output, tool skill loading or the coordinator's narration.
- Add tests alongside code, including negative cases, revocation, missing broker, forbidden access, timeouts, budget exhaustion and rollback.
- Make small, reviewable PRs. Update `harness/build-log.md` and the linked issue at each completed phase; preserve Git history. Record exact tests and observed PASS/FAIL/HOLD.
- If credits, session steps or external access end, leave a reproducible handoff in `harness/build-log.md` with branch, commit, tests, remaining tasks, blockers and precise next action. Do **not** claim ongoing background work or percentage completion without measured evidence.

## Completion definition
Do not label the project `DONE` until every mandatory exit gate in `docs/CODEX_EXECUTION_PLAYBOOK.md` is evidenced, native Linux acceptance and rollback pass, and the owner explicitly approves release. Unsupported optional-provider login mechanisms remain visibly unsupported, never faked.
