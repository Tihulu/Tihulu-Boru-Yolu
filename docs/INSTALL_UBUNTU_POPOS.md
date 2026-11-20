# Pop!_OS and Ubuntu staged installation (non-destructive)

Target: Ubuntu LTS and Pop!_OS 24.04 or other supported Ubuntu-derived releases, Linux x86_64 first. Validate distribution-specific package support and pinned versions before using these steps. **Nothing in this repository auto-installs software.**

## Phase 0 — inventory and rollback

- Confirm versions and running sessions for Jan, OpenCode, Python, Git, Kandev and Langflow *locally*; do not upload inventories.
- Confirm ports available and no active run will be interrupted.
- Record supported release URLs/checksums and create owner-only backups of *configuration and metadata* (not necessarily huge GGUF weights) using a locally reviewed backup method.
- Verify a restore test in disposable locations; do not remove or overwrite live data.
- Start a separate workspace/repository checkout; keep old models and chats untouched.
- Approve only non-disruptive installation steps before running them.

## Phase 1 — Kandev pilot

Download the official pinned, release-verified Linux x64 binary/archive or desktop package from upstream. Do not pipe unknown installation scripts into a privileged Shell. Kandev defaults may bind `0.0.0.0`; force loopback:

~~~bash
KANDEV_SERVER_HOST=127.0.0.1 kandev
~~~

This command is **illustrative** and only usable after official binary installation and approval. Use a separate Kandev state directory. Do not install a system service or enable auto-start. Do not authorize Kandev auto-installs, remote SSH, shared-host runners, or agents in existing private repos in the first pilot.

Acceptance: service restricted to loopback, synthetic Kanban created, no existing sessions affected, clear stop procedure.

Upstream: https://kandev.ai/docs/cli

## Phase 2 — Langflow pilot

Use a dedicated, non-system Python environment and a version pinned from an official release. Supported installation options include `uv`/pip environment or rootless container; choose after checking system and local API access.

For a native environment (example only):

~~~bash
uv venv .venv-langflow
uv pip install --python .venv-langflow/bin/python "langflow==<PINNED_VERIFIED_VERSION>"
LANGFLOW_HOST=127.0.0.1 LANGFLOW_AUTO_LOGIN=False \
  .venv-langflow/bin/langflow run --host 127.0.0.1 --port 7860
~~~

Replace the placeholder version with a verified release before execution. Secure local admin credentials and app secret **outside git**; run under unprivileged account. Keep automatic updates and internet exposure disabled. Review current `LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS` and `LANGFLOW_SSRF_ALLOWED_HOSTS` settings; enable required Jan loopback access *narrowly*, never globally whitelist hosts.

Acceptance: auth enabled, loopback only, single synthetic no-tools flow saved, no filesystem/network tools exposed, Jan text-only response verified.

Upstream: https://docs.langflow.org/getting-started-installation/ ; https://docs.langflow.org/api-keys-and-authentication

## Phase 3 — Jan/OpenCode read-only linkage

- Verify Jan API endpoint and exact model IDs locally. A model listed by `/models` may not be loaded.
- Select one small local model for first test and **avoid multiple high-memory model loads**.
- In Kandev, register a **separate disposable OpenCode agent profile** only after checking the installed CLI adapter version. Never mutate existing global TIHULU-AUTO profiles.
- In Langflow, create a tool-free Jan chat node with approved localhost endpoint.
- Verify independent 3-message/retained-context tests and model-switch test.
- Log only synthetic test markers and aggregate results.

## Phase 4 — broker and adapter (not available yet)

Only after separate source reviews and security tests:
1. install a dedicated broker in a confined service user/environment;
2. use owner-authenticated consent UI, restricted socket permissions and OS sandbox;
3. test denial paths before enabling cloud Shell;
4. connect Kandev workflow events to Langflow through a supported adapter;
5. do not enable broad localhost proxies or Docker socket mounts.

Cloud Shell profile remains OFF until the owner deliberately enables it and test evidence supports isolation and revocation.

## Offline-first operation

A local Jan-only pipeline can operate without internet once required packages/models are installed. GitHub PR operations, cloud LLM endpoints and release downloads necessarily require network when invoked. Do not call external model providers in LOCAL_ONLY.

## Port hygiene

Typical development ports: Jan API `1337` (verify locally), Kandev `38429`, Langflow `7860`. These are *examples*, not claims about active processes. Do not expose interfaces via `0.0.0.0`, Docker unqualified port publishing, Tailscale, SSH reverse tunnel or a reverse proxy without a separate authenticated network plan.

## Rollback

Stop **only** newly launched Kandev/Langflow/Boru services; remove their dedicated test virtual environment/state after backing up any desired test work. Leave Jan weights, Jan service, OpenCode configuration, providers, active sessions and unrelated apps untouched. No automatic service restart on uninstall.
