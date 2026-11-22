# TIHULU Boru Yolu

**Local-first, user-controlled orchestration for AI coding agents, visual workflows, and hybrid local/cloud models.**

> Status: **Boru Core P1–P10 source slices are implemented and unit/integration tested locally**
> (646 tests, CI green). What exists is a local, offline-first core with typed contracts,
> durable task state, a bounded provider layer, mode-aware routing with budgets, a DAG planner,
> a fail-closed authorization chain, grant-bound GitHub/GitLab connectors, a loopback dashboard
> and user-space install/rollback scripts. Two live gates have passed on this machine:
> direct Jan 3-turn chats (A21) and a real OpenCode child session (A23).
> Nothing here is a release: live acceptance, independent security review, the sandbox runtime,
> provider OAuth, the remote half of the Privacy Bridge and owner release approval remain **HOLD**.
> Never interpret a workflow diagram or configuration example as an enforced security boundary.

## Purpose

TIHULU Boru Yolu has its **own independent Boru Core** for routing, budgets, scheduling, and subagent orchestration. It optionally connects **Kandev** (tasks, roles, reviews), **Langflow** (visual pipelines), **OpenCode** (standalone coding agents), and **Jan** (standalone local models). **TIHULU-AUTO is an optional legacy integration, never a required dependency or a release blocker.** OpenCode and Jan keep working when Boru Yolu or TIHULU-AUTO is offline, uninstalled, or unfinished.

It supports both preferences:
- **Local-isolated Shell (default):** only an independently authorized local executor may invoke host tools; cloud models receive minimum necessary, validated information.
- **Cloud Shell opt-in:** an owner can choose to allow a cloud-driven agent to request Shell operations **inside a separately isolated, project-scoped sandbox**, only through a trusted authorization broker and explicit, short-lived consent. No cloud-to-host Shell shortcut; no automatic escalation.

Cloud *inference*, Shell *execution*, and private-data *disclosure* are **three independent controls**, not one ambiguous "local/cloud" toggle. **Optimization is a fourth independent axis**: AUTO, ECONOMY (token-optimized), BALANCED, PERFORMANCE, and MANUAL never grant access to Shell, cloud inference, connected accounts or additional private data. Losing a provider or falling back to another cannot silently escalate permissions. These owner requirements are preserved independently of the unfinished TIHULU-AUTO project.

## Components and ownership

| Component | Responsibility | Not a security guarantee |
| --- | --- | --- |
| Kandev | Kanban, coding-agent profiles, workflow steps, worktrees, review and QA | A Kandev agent can invoke tools; task stages alone do not isolate Shell |
| Langflow | Drag-and-drop DAGs, routing visualization, typed flow inputs/outputs | A flow node is not a trusted permission broker |
| Boru Core (native) | Model catalog, mode-aware routing, subagent scheduler, fallback, budgets and resource leasing | A model prompt cannot authenticate an executor |
| TIHULU-AUTO (optional) | Legacy workflow/agent bridge, import or migration when independently verified | Not a prerequisite, single routing authority or fallback requirement |
| OpenCode | Primary/subagent sessions, coding workflows and provider adapters | A skill is not a subagent; effective permissions must be tested |
| Jan | Existing local OpenAI-compatible model API | An accessible model ID does not prove loaded availability or tool compatibility |
| Trusted broker / Privacy Bridge | Consent verification, execution restrictions, output release policy and audit | **Not implemented or validated yet** |

**Dependency rule:** neither OpenCode nor Jan depends on Boru Core or TIHULU-AUTO; Boru Core must start and run without TIHULU-AUTO installed. Optional adapters are disabled by default and cannot change standalone app settings.

## Policy choices

| Execution profile | Cloud inference | Shell control | Local sensitive output |
| --- | --- | --- | --- |
| `LOCAL_ISOLATED` (**default**) | Optional, governed separately | Trusted local worker only | Minimized/typed; no raw forwarding |
| `HYBRID_PRIVATE` | Allowed by owner | Trusted local worker only | Minimal approved disclosure |
| `CLOUD_SHELL_APPROVAL` (**opt-in**) | Allowed | Cloud-driven requests only via owner-approved *sandbox broker* | Approved scope only; sanitize tool results |
| `CLOUD_SHELL_TRUSTED` (**advanced opt-in**) | Allowed | Expiring, narrow, revocable sandbox capability | Disclosure remains separately controlled |

`CLOUD_SHELL_TRUSTED` never means unrestricted host Shell; it is a convenience policy for preapproved *sandbox-scoped* operations. If unrestricted host access is desired, it is explicitly **out of scope for the initial release**.

Routing presets `AUTO`, `ECONOMY`, `BALANCED`, `PERFORMANCE` and `MANUAL` are **orthogonal** to these security profiles. `LOCAL_ONLY` is a separate inference restriction.

## What you can run today

~~~bash
python3 scripts/check_project.py              # static manifest + sample policy invariants
python3 -m unittest discover -s tests         # 643 unit/integration tests (offline, hermetic)
python3 -m boru demo                          # fixed offline synthetic task -> REVIEW
python3 -m boru --config examples/core.example.json --state-dir local-state run --task task.json
python3 -m boru --state-dir local-state plan --file plan.json
python3 -m boru resources                    # resource profile, lease bounds, host RAM/swap (no host state touched)
python3 -m boru queue                        # tasks awaiting an explicit review
python3 -m boru review --task-id <id> --accept
python3 -m boru cancel --task-id <id>        # cancel a queued/held task
python3 -m boru audit --audit-dir local-state/audit --limit 32
scripts/install_boru.sh --dry-run             # user-space install/rollback (no sudo, no service)
python3 scripts/evidence.py                   # sanitized evidence block, exit 0 when mandatory checks pass
~~~

`local-state` must be an existing owner-only directory. Every completed reply stays in `REVIEW`
until you accept it with `boru review --task-id <id> --accept`; simulated results are never
relabelled as live.

### Resource profiles (performance knob, never an authorization axis)

Boru Core ships four resource profiles. They size Boru's own leases and its idle
policy and can never widen inference, execution, Shell or disclosure rights.

| Profile | Logical agents | Large local models | Idle behaviour |
| --- | --- | --- | --- |
| `PERFORMANCE` | 6 | 2 | never evict; models kept warm for the next task |
| `BALANCED` (default) | 4 | 1 | a kept-warm model lease is released after 900 s idle |
| `RESOURCE_OPTIMIZED` | 2 | 1 | a kept-warm model lease is released after 60 s idle |
| `CUSTOM` | owner-set (1..6) | owner-set (0..2) | owner-set; either evict idle or keep warm |

Set `resource_mode` (and `resource_overrides` for `CUSTOM`) in your configuration,
then run `python3 -m boru resources` to see the profile, the lease bounds and the
host RAM and swap this process can see. Releasing a *loaded model's* memory needs a
provider lifecycle endpoint: Boru releases its own lease and asks the provider
(`ChatProvider.unload`), and a provider with no documented endpoint - Jan today -
refuses with `unsupported_capability` instead of guessing. See
`docs/ROUTING_AND_RESOURCES.md`.

## Codex implementation handoff

- **[Single Codex start/resume prompt](docs/CODEX_START_PROMPT.md)** — hand to Codex after opening this repository.
- **[End-to-end execution playbook](docs/CODEX_EXECUTION_PLAYBOOK.md)** — P0–P10 development, dependencies, security gates and release definition.
- **[Persistent Codex instructions](AGENTS.md)** and **[evidence-based build log](harness/build-log.md)** — ensure each new session resumes without restarting or declaring untested work done.
- The planning baseline is **draft PR #1**; implementation continues in **draft PR #14** on branch
  `p1/boru-core-vertical-slice`. Live local Shell, provider credentials, the sandbox runtime and
  release approval are separate, owner-gated steps recorded in `harness/build-log.md`.

## Repository map

- [Architecture](docs/ARCHITECTURE.md)
- [Security profiles and consent](docs/SECURITY_MODES.md)
- [Privacy Bridge contracts](docs/PRIVACY_BRIDGE.md)
- [Routing, budgets, GPU lifecycle](docs/ROUTING_AND_RESOURCES.md)
- [Kandev / Langflow / OpenCode / Jan integration](docs/INTEGRATIONS.md)
- [Pop!_OS and Ubuntu setup](docs/INSTALL_UBUNTU_POPOS.md)
- [Implementation roadmap](docs/ROADMAP.md)
- [Acceptance and test matrix](docs/ACCEPTANCE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Operations, rollback and migration](docs/OPERATIONS.md)
- [Architecture decisions](docs/ADRS/0001-control-plane-and-trust.md), [Shell policy decision](docs/ADRS/0002-shell-execution-profiles.md), [Boru Core independence (ADR-0003)](docs/ADRS/0003-boru-core-independence.md), [Preserved optimization, privacy and Shell policies (ADR-0004)](docs/ADRS/0004-preserve-modes-and-privacy.md)
- [Example configuration](examples/boru-yolu.example.json), [Flow sketch](examples/visual-flow.mmd)
- [Static contract checks](scripts/check_project.py) and [unit tests](tests/test_contract.py)

## Current boundaries

1. Keep production OpenCode, Jan, models and chat sessions untouched at first.
2. Bind new web services to loopback; no auto-start, cloud sync, remote sharing or exposed API by default.
3. Do not enable Kandev/agent auto-install or workspace-wide Shell privileges.
4. Do not infer availability or remaining credits from a model registry.
5. Do not send configuration files, raw terminal logs, directory inventories, credentials or private task content to cloud services by default.
6. Backups, real execution, deployments and security acceptance are **HOLD** until verified on a controlled Pop!_OS/Ubuntu machine.

## Developer sanity check (source-only)

~~~bash
python3 scripts/check_project.py
python3 -m unittest discover -s tests -v
~~~

This checks only the repository's example contracts; it does **not** start Jan, Kandev, Langflow, OpenCode or any executor.

## Upstream references

- [Kandev CLI and security notes](https://kandev.ai/docs/cli)
- [Kandev agents and profiles](https://kandev.ai/docs/agents-and-profiles)
- [Langflow installation](https://docs.langflow.org/getting-started-installation/)
- [Langflow API/authentication](https://docs.langflow.org/api-keys-and-authentication)
- [Langflow OpenAI-compatible endpoints](https://docs.langflow.org/bundles-openai-compatible)
- [OpenCode tools and subagents](https://opencode.ai/docs/tools/)

Kandev is AGPL-3.0 and Langflow is MIT at the time of planning. They remain external upstream projects; no upstream source is vendored here. The license for *this repository* must be chosen separately before release.
