# Privacy Bridge: minimum necessary information

## Scope

Every local-to-cloud payload from Shell, source files, test results, folders, repository metadata, logs, process state, devices, environment variables and model runtime diagnostics must pass a **trusted, deterministic** release gate. Generic PII scanning or "the model summarized it" is not enough.

There is no production Privacy Bridge in this repository yet. Prior TIHULU-AUTO source-only prototypes can be evaluated for reuse, but must pass import, adversarial, consent and OS isolation gates first; do not copy unverified prototype security assumptions into deployment.

## Five-stage pipeline

1. **Request shaping:** a cloud agent sends a typed question such as "does the approved project folder exist?" or "did the test suite pass?" instead of a broad `ls -R` or complete log request.
2. **Local acquisition:** independently authorized worker fetches only relevant data inside allowed scope; raw data stays on the controlled host.
3. **Local reduction:** deterministic parser extracts fields for that question; prefer `boolean`, `count`, `status code` and restricted enums.
4. **Release authorization:** trusted broker validates field allowlist, provenance, policy, recipient and if necessary a specific owner-issued disclosure grant.
5. **Cloud delivery:** send only the validated typed object; log released field names, count and decision, never private payload contents in public logs.

## Example contracts

Existence check:
~~~json
{"request_id":"example-1","operation":"target_exists","target_alias":"approved-project","wanted_fields":["exists"]}
~~~
Safe response:
~~~json
{"request_id":"example-1","status":"success","fields":{"exists":true}}
~~~

Test diagnostics:
~~~json
{"request_id":"example-2","status":"failed","fields":{"test_count":12,"failed_count":1,"error_category":"import_error"}}
~~~

**Do not** include home paths, full directory listings, hidden filenames, local account names, full test traceback, all devices, API keys or full source files merely because they were part of the local command output.

## Progressive disclosure

- **L0:** boolean/status/count only.
- **L1:** narrowly required non-sensitive detail such as the missing dependency's public package name.
- **L2:** protected excerpt or file/stack/context requires explicit field-level approval, exact recipient and expiry.
- Denied or unavailable approval means **no disclosure**; work may continue locally if policy permits.

## Prevent common bypasses

- The adapter must not place private text inside Kandev task titles, Langflow prompts, GitHub issues, model telemetry or unredacted tracing.
- No direct cloud requests from Langflow components using unrestricted read/file/shell tools in restricted profiles.
- Protect against structured output with extra keys, oversized strings, path traversal, Unicode obfuscation, nested blobs and unknown schemas.
- Do not redact after the network request was made; inspect **before** release.
- File/network and process-level restrictions must be independent of a model's willingness to comply.
- Test both success paths and failures/retries/cancellations for output leaks.
- A cloud Shell grant authorizes execution control **only within the sandbox**; disclosed output is a separate decision.

## Status and hard gates

| Capability | Current state |
| --- | --- |
| Example typed result design | Documented |
| Independent authenticated worker | HOLD |
| Consent authority / revocation / replay protection | HOLD |
| Deterministic parser + per-field release code | HOLD |
| Confined Shell executor / cloud Shell sandbox | HOLD |
| End-to-end local->cloud minimal disclosure test | HOLD |

No output privacy promise is enforceable until those gates pass on a real host.
