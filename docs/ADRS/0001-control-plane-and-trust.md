# ADR-0001: Separate UI, routing and authorization owners

- Status: **Superseded in part by [ADR-0003](0003-boru-core-independence.md) (routing ownership only); archived design retained**
- Date: 2026-11-20

## Context

The existing TIHULU-AUTO goal is local/cloud AI orchestration with model-appropriate routing, token optimization, and privacy-preserving terminal workflows. Kandev and Langflow offer useful UI and workflow capabilities but not, by themselves, an independently enforced permission boundary.

## Decision

Use **Kandev** for task/worktree/agent management, **Langflow** for visual flow definitions, **TIHULU-AUTO** as the *only* model-routing authority, and a separately verified **trusted local broker** for execution and data release. Keep OpenCode and Jan as existing independent providers. Introduce a narrowly scoped Boru Adapter for Kandev task lifecycle -> Langflow run integration.

## Alternatives

- Replacing OpenCode and Jan: rejected because stable-first preservation is required.
- Letting Langflow be the router and security gate: rejected because it would duplicate routing decisions and conflate visual logic with trust enforcement.
- Prompt-only privacy instructions: rejected because a model can ignore or be tricked by instructions.
- Automatic Kandev agent host Shell: rejected as the default because runtime permissions may exceed intended tool scope.

## Consequences

Additional adapter/broker engineering; better separation of concerns; incremental testability. All components can remain down/absent while Jan and OpenCode continue operating normally.

## Verification required

Kandev workflow hook API, Langflow local API, OpenCode effective subagent tool access, Jan chat API, broker runtime and OS confinement. No implementation is assumed completed.
