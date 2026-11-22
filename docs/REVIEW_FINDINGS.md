# Gate 1 review findings — as recorded by the working notes

The first independent review of `cc73940` returned **FAIL** with findings
numbered F01–F22. The report itself arrived through the review channel and is
not stored in this repository, so this file records the findings **as captured
in the working notes** with their remediation status.

Two findings — **F06** and **F20** — are recorded as existing in the reviewer's
report but carry no individually captured description in the working notes.
They are listed as *to re-confirm* rather than described from memory: the
re-review must re-issue the canonical finding text, and any behaviour it names
must be re-tested against this head. Nothing in this repository claims those
two are closed.

| # | Severity (as recorded) | Finding (as recorded) | Remediation | Commit | Status |
|---|---|---|---|---|---|
| F01 | Blocker | An executor receipt was never authenticated | `boru/authorization.py` HMAC-signed, request-bound receipts; the executor verifies under the worker authorization key before any filesystem access | `e449d17` | Closed (re-confirm) |
| F02 | Blocker | A worker id could traverse the registry directory | A worker id is one opaque segment; the record file must stay inside the registry | `e449d17` | Closed |
| F03 | Blocker | Consent was not bound to the resource alias or the disclosure level | Grants bind recipient, task, operation, alias, field and level; a weaker grant never covers a wider level | `e449d17`, `8e0869b` | Closed |
| F04 | Medium | A repository reference was parsed twice (check and path construction) | `check_call` returns the validated slots; both providers build their path from exactly those slots | `93fb0de` | Closed |
| F05 | Medium | A workflow dispatch body was not validated before the transport | A dispatch body is validated first: its `ref` must be the granted reference and its inputs bounded | `93fb0de` | Closed |
| F06 | — | **Recorded in the report; not individually described in the working notes** | The broker now authenticates an identity against the owner registry (an asserted identity is only usable in-process and can never widen the broker's own worker) — verify this is the finding | `e449d17`, `79abd23` | **To re-confirm** |
| F07 | Medium | `call()` did not enforce the grant's account identity | `call()` verifies the account behind the token once per provider and refuses a mismatch before any repository request | `93fb0de` | Closed |
| F08 | Blocker | Alias traversal followed symlinks | The alias root is opened with `O_DIRECTORY\|O_NOFOLLOW` and a target is resolved component-wise with `dir_fd` + `O_NOFOLLOW` | `e449d17` | Closed |
| F09 | Blocker | The ledger stored unsanitized subjects | Stored identifiers are sanitized (a path, URL or token fragment keeps no separator that could make it a filesystem or network reference) | `e449d17`, `8e0869b` | Closed |
| F10 | Medium | Nested private fields validated; results saved before verification | Recursive bounded payload validation; a failed verification is never persisted as a result | `93fb0de` | Closed |
| F11 | Medium | The consent level was not bound | Both consent stores bind the disclosure level and the gate passes the requested level | `e449d17`, `8e0869b` | Closed |
| F12 | Medium | A revoked grant id could be re-issued | A grant id is immutable once issued; re-issue is refused | `8e0869b` | Closed |
| F13 | Medium | Nonfinite timestamps could issue a usable identity | A nonfinite timestamp yields a record that refuses at every `valid()` check | `e449d17`, `8e0869b` | Closed |
| F14 | Medium | The loopback surface spawned unbounded threads | A bounded semaphore; beyond the bound the surface denies `service_busy` | `e449d17` | Closed |
| F15 | Medium | Response handling was unbounded | Responses are capped and the content type is validated | `93fb0de` | Closed |
| F16 | Medium | Polling replayed evicted event ids | The seen registry is bounded and never forgets; a full registry refuses new work | `93fb0de` | Closed |
| F17 | Medium | Anti-replay state was unbounded | Used nonces are pruned to a documented bound | `e449d17` | Closed |
| F18 | Medium | Read metadata was synthesized | Real bounded `size`/`line_count` from `fstat` and bounded reads | `e449d17` | Closed |
| F19 | Medium | Sizing limits had no upper bound | `max_result_fields` 1..32, `max_retries` 0..8 | `93fb0de` | Closed |
| F20 | — | **Recorded in the report; not individually described in the working notes** | The outbound boundary classification is now derived from the payload actually sent, and the classified messages are the ones transmitted — verify this is the finding | `93fb0de` | **To re-confirm** |
| F21 | Blocker | Evidence class came from a provider's claim | The recorded class is derived from provider provenance; a reply's own claim is not trusted | `93fb0de` | Closed |
| F22 | Blocker | The outbound payload class was asserted, not classified | `classify_payload` derives the class from the actual messages | `93fb0de` | Closed |

The reviewer's 20 regression probes (checked in as
`tests/test_review_regressions.py`) pass 20/20 on this head; they are the
executable half of this table, but a probe passing is not a verdict.
