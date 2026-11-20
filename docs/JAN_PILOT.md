# Direct Jan text-only pilot — plan and current status

Status: **HOLD — no live Jan call has been made.** The transport is
implemented and tested against a loopback fixture; the pilot below still needs
an owner-approved run.

## Why explicit operator configuration is required

Jan's local API server can be configured to proxy **remote** providers and to
execute MCP tools server-side. A loopback URL therefore does not prove a model
is local. `boru/providers/jan.py` refuses to guess: it requires an explicit
endpoint, an explicit model allowlist and `tool_execution_disabled=True`.

Optional discovery step (owner opt-in): add `"allow_discovery": true` to the
provider entry, then run `python3 -m boru --config jan.pilot.json --state-dir local-state providers`
and `python3 -m boru --config jan.pilot.json --state-dir local-state run --task discovery.json`
with a task whose only purpose is to print the allowlisted models. Without that
flag Boru never queries `/v1/models`.

## Preconditions (owner-verified, then recorded)

1. Jan is running and reachable on a numeric loopback endpoint, for example
   `http://127.0.0.1:<port>/v1` (fill in the real port from the Jan UI).
2. The selected model is a **local** model, present in Jan's model list.
3. Jan's *Execute tools on server* setting is **disabled** for this pilot.
4. No remote provider is routed through this endpoint.
5. A dedicated owner-only state directory exists for the pilot.

## Run

~~~json
{
  "version": 1,
  "policy": {"optimization_mode": "AUTO", "inference_scope": "LOCAL_ONLY",
             "execution_profile": "LOCAL_ISOLATED", "disclosure_policy": "MINIMUM_NECESSARY"},
  "request_timeout": 60.0,
  "max_output_tokens": 256,
  "providers": [
    {"kind": "jan", "endpoint": "http://127.0.0.1:<port>/v1",
     "local_model_ids": ["<exact-model-id>"], "tool_execution_disabled": true}
  ]
}
~~~

~~~bash
python3 -m boru --config jan.pilot.json --state-dir local-state providers
python3 -m boru --config jan.pilot.json --state-dir local-state run --task chat1.json
python3 -m boru --config jan.pilot.json --state-dir local-state status --task-id chat-1
~~~

`chat1.json`:

~~~json
{"task_id": "chat-1", "goal": "3-turn synthetic memory check",
 "payload": {"messages": [
   {"role": "user", "content": "Remember only the word blue."},
   {"role": "assistant", "content": "Understood."},
   {"role": "user", "content": "Which word should you remember? Reply with that single word."}]}}
~~~

## Evidence to record

From `status --task-id chat-1`: `state` (expected `REVIEW`), `provider`
(expected `jan`), `model_id` (must equal the requested ID), `evidence_class`
(expected `direct`), `usage_if_observed` (present only if Jan reported it) and
`live_acceptance` (always `HOLD` until the owner reviews). Record the request
ID from `evidence_refs` as the provider-side reference. Never invent a child
session ID: a plain HTTP reply has `child_session_ref = null`.

Three turns confirm conversation handling; a second run with a different model
confirms model identity is not confused. A deliberately wrong model ID must be
refused before any call.

## Status values

- Transport + fixture tests: implemented, passing (MOCK/FIXTURE).
- Live Jan pilot: **HOLD**, pending owner approval and an explicit endpoint,
  model ID and tool-execution confirmation.
- Standalone Jan/OpenCode verification (A22, A21): **HOLD**.
