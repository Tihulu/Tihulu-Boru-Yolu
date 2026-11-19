# Kandev, Langflow, OpenCode and Jan integration contracts

## Kandev: task/worktree/agent UI

Use Kandev as an external control-plane product, not a vendored dependency. As of planning, Kandev supports OpenCode agent profiles and multiple execution runtimes, including local host and Docker. The initial pilot must prefer **read-only task review** and a disposable test workspace; never point it at sensitive live workspace configurations for unrestricted agent access.

Check Kandev version, OpenCode adapter version and workflow format before importing a workflow. An apparent "agent profile" does not itself prove a Jan-backed child session. Validate actual provider/model identity in logs **locally**.

Upstream: https://kandev.ai/docs/agents-and-profiles and https://kandev.ai/docs/workflow-import-export.

## Langflow: visual orchestration design

Use Langflow's OpenAI-compatible provider or a supported custom component with a configured endpoint for Jan. Before enabling localhost HTTP targets, inspect current Langflow SSRF protection; its HTTP host allowlisting must be an explicit operator decision, not a global unrestricted network bypass. Use a dedicated local API token if the endpoint supports one.

Run a text-only flow, `user input -> Jan local model -> response`, with no file/shell tools. Validate via actual Langflow run output, not model claim.

Upstream: https://docs.langflow.org/bundles-openai-compatible and https://docs.langflow.org/api-reference-api-examples.

## OpenCode: preserve existing state

- Keep Jan/OpenCode independently runnable.
- Use **subagent** tool to invoke a registered child agent; `skill` is instructions, not actual delegation.
- Keep effective V2 agent permissions narrow. Record version and resolve any differences in permission schemas from the installed version rather than copying old config.
- Do not edit global provider credentials, installed model registry, active sessions or agent configs during initial pilot.
- A success from generic `general` subagent is not proof a custom TIHULU-AUTO child works.
- Cloud model provider and local Jan model must both have verified actual tool invocation when needed.

Upstream: https://opencode.ai/docs/tools/.

## Jan model integration

Jan is already installed in the intended host; use its existing OpenAI-compatible API **read-only** for model discovery. Example loopback base URL `http://127.0.0.1:1337/v1` is illustrative and must be confirmed locally. Do not assume the API is active or a listed model is loaded. Keep data/config in place; no model downloads or driver updates in integration pilot.

Never send Jan model IDs, hardware status or host environment as an unrestricted list to cloud automatically. IDs are technical metadata, but only task-relevant fields should be disclosed.

## Kandev <-> Langflow bridge: deliberately not a presumed feature

A small **Boru Adapter** must integrate *documented* Kandev task/workflow events with Langflow's authenticated flow-run API, using:
- a narrowly scoped local listener or an owner-invoked action;
- stable task IDs, idempotency keys and workflow revision;
- typed inputs/outputs; no raw tool transcript forwarding;
- authenticated caller identity and least-privileged API credentials;
- explicit user approval when operating in elevated profile;
- retries with dedupe, acknowledgements, cancellation and failure classification.

No verified out-of-box Kandev -> Langflow plugin is assumed. If the installed Kandev version lacks the needed hook, start with a **manual task-to-flow handoff** and leave automation HOLD.

## Workflows

Initial: Kandev `Plan -> Work (text only) -> Review -> QA`; Langflow visual `classification -> route -> local model -> validate result`. Production: add broker approval node **as a UI request**; enforcement stays in a trusted service.

No external account required for the local controls. If a cloud model is selected, provider authentication is separate and owner-configured.
