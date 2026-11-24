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

## 3-C. Gate 1 second re-review of `cedb56fb` (24 November 2026) — FAIL / DO NOT APPROVE

The reviewer verified the CI run for this head independently (701 tests, 700
passed, 1 skipped, static validation succeeded) but **could not clone the
repository** — `github.com` did not resolve in its environment, so it inspected
pinned source through the GitHub connector and exercised source excerpts in an
isolated harness with synthetic inputs. It says so explicitly and claims no
full-suite run. Its verdict was **FAIL / DO NOT APPROVE**.

It accepted on static evidence: **F06, F14, F15, N01, N03, N04**.
It marked partially remediated: **F03, F17, F20, N02**.
It marked failed: **F07, F12, N05**.
It issued five new findings: **N06, N07, N08, N09, N10**.

Each finding below was **reproduced against this tree first** (an executable
probe whose output was read, not assumed), then remediated, then closed with a
named negative regression test. The mapping is complete: every finding the
reviewer raised names the tests that assert its closure, and no test is claimed
to cover a finding it does not exercise (N10).

| # | Severity | Finding (as reported) | Reproduced? | Remediation | Named regression tests |
|---|---|---|---|---|---|
| F03 | High (partial) | Alias binding fixed, but the recipient could be omitted in a check | Yes — `check(recipient=None)` matched a grant bound to `alice` | The recipient is mandatory in both stores; there is no recipient-less query, and the broker refuses to construct without an explicit `consent_recipient` | `tests/test_review3_regressions.py::F03RecipientBindingTests` (3 tests) |
| F07 | High | The identity cache bound only the token, not the verified account; a missing credential passed the guard | Yes — a second account behind one token was accepted; a configured-but-absent token passed | The remembered identity is the verified **(token fingerprint, account)** pair; a configured channel with no credential value denies `credential_missing` | `...::F07IdentityGuardTests` (2 tests, GitHub and GitLab) |
| N02 | Medium (partial) | Discovery accounting existed but inherited the F07 guard defect | Yes — discovery accepted a mismatched account | Discovery calls the same identity guard and the same atomic reservation as every other externally connected path | `...::F07IdentityGuardTests::test_n02_discovery_inherits_the_identity_guard` |
| F12 | Medium | The in-memory consent store allowed a revoked grant id under another task | Yes — reissue under `task_id="t2"` was granted | A grant id is globally unique in the in-memory store too, and every remaining binding (recipient, task, field) is matched | `...::F12ConsentIdentityTests` (3 tests) |
| F17 | Medium (partial) | Migrated nonce rows with zero expiry could never expire | Yes — a zero-expiry row survived every retention pass and filled the bound | The v2→v3 migration binds each nonce to its grant's expiry (an orphan becomes prunable at once), and retention also prunes legacy no-expiry rows | `...::F17MigratedNonceTests` (2 tests) |
| N05 | Medium | A restored polling history was fully materialized before its bound was checked | Yes — 10,000 entries consumed before the 8,192 rejection | The bound is enforced while the source is consumed: the refusing entry stops the iterator | `...::N05BoundedRestoreTests` (2 tests) |
| N06 | High | Call ceilings were not atomic | Yes — a 20-thread race reserved 6+ calls against a 5-call ceiling | The ceiling check and the reservation are one atomic step under the provider's lock, before any transport exists | `...::N06CallCeilingTests` (2 tests, GitHub and GitLab) |
| N07 | High | A workflow name and a run id were not verified as belonging together | Yes — `get_run` with only a `run_id` was accepted | Every workflow-addressed operation — the run operations included — requires its granted workflow, so a run is reached only through it | `...::N07RunScopeTests` (3 tests) |
| N08 | High | A validated reference could diverge from the transmitted write body | Yes — `create_pull` sent `base=develop` on a `main` grant | Per-operation typed write-body contracts: the documented keys only, and reference-carrying keys must equal the granted reference; `check_write_body` runs before any transport | `...::N08WriteBodyTests` (5 tests, GitHub and GitLab) |
| N09 | Medium | Future-issued grants were accepted | Yes — `issued_at = now + 86400` passed `permits()` | `permits()` enforces `issued_at <= now < expires_at` | `...::N09GrantValidityTests` (3 tests) |
| N10 | Medium | Regression-coverage claims exceeded demonstrated coverage | Yes — the old table claimed closures for findings whose behaviour was still reachable | This section is a complete finding-to-test mapping, re-derived from the executed suite rather than from intent | `tests/test_review3_regressions.py` (26 tests) |

**Recovered historical findings** (the reviewer recovered them from historical
records; the verbatim original reports were not available for comparison):
F06 (optional registry allowed forged worker scopes) and F20 (evidence pinned
to a different commit). The recovered F06 reproducer — a worker with scope A,
an allowlist containing A and B, and a request for B declaring scope B — is
asserted denied in `tests/test_rereview_regressions.py::F06Tests`; the F20 pin
contract is asserted in `tests/test_rereview_regressions.py::F20Tests`. Both
remain marked *re-confirm* pending the original reviewer's canonical text.

**Scope of this remediation, stated honestly:** every fix is source-level and
unit-tested against test-owned transports. No live provider, GitHub token or
host shell was used. Host-level process authentication, OS confinement, live
provider behaviour and clean-machine acceptance remain separate HOLD gates and
are not affected by this work.

**Next step:** push the exact head, verify its CI, and request a third
independent review against it.
