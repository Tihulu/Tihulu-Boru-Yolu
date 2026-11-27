# Bridge contract candidate (issue #17)

This separate development branch proposes offline metadata contracts for the
reciprocal Jarvis/Boru bridge. It does not modify the reviewed PR #14 branch
or enable any runtime capability. CLI-Anything is strictly optional, including
at release; Pi, DSH, Langflow and Kandev remain independent optional adapters.

## Implemented candidate

* Schema 1 engine manifest with a finite operation vocabulary and strict fields.
* Immutable task owner, delegation history and bounded hop limit.
* Cycle rejection and compatibility checks, not authorization.
* Offline positive/negative unit tests; no socket, subprocess, credentials or
  runtime integration.

Do not deserialize a peer-provided delegation history into trusted routing
state. The future service must reconstruct history from its authenticated,
durable task ledger. A manifest never grants access.

## Remaining mandatory bridge work

1. Durable idempotency, deadlines and authoritative task state.
2. Authenticated peer identities, per-operation grants, revocation and recipient
   disclosure enforcement through the existing broker.
3. Native task submit/status/events/cancel and checkpoint-aware pause/resume.
4. Jarvis peer adapter and optional MCP/API adapter with separately approved
   connection; no existing chat access or credential reuse implied.
5. UI and two-direction disposable acceptance, replay, cancellation, crash,
   and privacy tests. Independent review of the changed code is required.

Status: SOURCE CANDIDATE. No live execution, authentication, installation or
release claimed. Tests must be run against the exact candidate revision.
