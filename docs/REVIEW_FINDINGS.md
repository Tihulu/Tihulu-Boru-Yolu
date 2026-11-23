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

## 3-B. Gate 1 re-review of `1617709` (23 November 2026) — FAIL / DO NOT APPROVE

The re-review could not clone the repository (DNS resolution failed in its
environment), so it read the connector source and the Actions logs rather than
executing the suite; it says so explicitly and claims no runtime PASS. Its
verdict was **FAIL**, with findings F03, F06, F07, F12, F14, F15 and F17 open
(High/Medium), F20 informational, and five new findings N01–N05. F06 and F20
are marked *reconstructed from current code*, not verbatim re-issues, because
the original reviewer's canonical text was never available in this repository.

Each finding was reproduced against this tree first, then remediated, then
closed with a named negative regression test (`tests/test_rereview_regressions.py`).

| # | Severity | Remediation | Commit |
|---|---|---|---|
| F03 | High | Alias mandatory and matched in both consent stores; a legacy alias-less row denies rather than matching | `176034a` |
| F06 | High | The registry record decides the permitted scopes; a request that declares more or less than it holds is refused, not ignored | `176034a` |
| F07 | High | The cached connector identity is a fingerprint of (provider, token); every externally connected path verifies identity and counts its usage | `176034a` |
| F17 | High | A used nonce outlives its grant; an expired grant's nonce is dropped; past the bound the store rolls back and refuses rather than evicting a live nonce | `176034a` |
| N01 | High | Grant timestamps must be finite, positive and ordered (a NaN expiry made every expiry comparison false) | `176034a` |
| N03 | High | The worker returns exactly the fields the receipt names | `176034a` |
| F12 | Medium | Schema version 3: grant_id globally unique, a version-2 store migrates and refuses an ambiguous history, a revoked id is a tombstone | `176034a` |
| F14 | Medium | Capacity is acquired before a thread spawns; an excess connection is refused on a drained request (and through the instance method — a bare name here killed the accept loop) | `176034a` |
| F15 | Medium | The GitHub exchange caps its HTTP error body, as the account request already did | `176034a` |
| N02 | Medium | Workflow discovery verifies identity and charges the grant | `176034a` |
| N04 | Medium | A dispatch with inputs and no owner-supplied declaration is refused | `176034a` |
| N05 | Medium | A restored polling registry is bounded as it is loaded | `176034a` |
| F20 | Informational | The review package now names the head it describes | this commit |

**Still required before Gate 1 can pass:** an independent re-review of this
tree, and the original reviewer's canonical text for F06 and F20.
