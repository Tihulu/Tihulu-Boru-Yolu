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

## 3-D. Gate 1 third review of `9b6ce534` (25 November 2026) — FAIL / DO NOT APPROVE

The reviewer verified the CI run for this head independently but **could not
clone the repository** (`Could not resolve host: github.com`), so it inspected
pinned source retrieved by exact SHA and executed isolated source-excerpt
probes. It states it cannot certify the 727-test count from CI metadata alone
and that a maintainer CI run is not an independent reproduction. Both
statements are recorded here rather than paraphrased away.

It accepted on static evidence: F03, F12, F17, N09. It retained the earlier
acceptance of F06, F14, F15, N01, N03 and N04 — those findings are not
reopened without evidence.

| # | Severity | Finding (as reported) | Reproduced? | Remediation | Named regression tests |
|---|---|---|---|---|---|
| N07 | High | A caller-declared workflow name was checked, but nothing established that the requested **run** belongs to that workflow: the run endpoint was built from the run id alone | Yes — the reviewer's own probe: `ci.yml` declared, run 42 of `other.yml` fetched | A run is addressed only after the **provider's own metadata** confirms ownership: the granted workflow's runs list (GitHub) or the granted reference's pipelines (GitLab). Missing or malformed evidence refuses (`run_ownership_unavailable`), a foreign run refuses (`run_not_of_workflow`), and a verified pair is remembered in a bounded memo | `tests/test_review4_regressions.py::N07RunOwnershipTests` (6 tests, both connectors) |
| N08 | High | Reference-carrying body keys were validated only **when present**, so omitting `branch`/`target_commitish` diverged from the granted reference; `create_branch` did not bind its source sha | Yes — omitted `put_file.branch`, omitted `create_release.target_commitish`, and a diverging `create_pull.base` were all accepted | Reference keys are **mandatory** per operation (`reference_required_in_body` when absent, `reference_not_granted` when divergent). GitHub's branch creation binds its source sha to the granted reference's own head taken from provider metadata, and the target must be a bounded, path-free `refs/heads` name | `...::N08WriteBodyTests` (7 tests) |
| F07 | High | The credential was read separately for fingerprinting, verification and the exchange, so a rotation mid-request could transmit an unverified credential | Yes — traced through the three read sites | The credential is read **once per authorized request** and that exact snapshot is fingerprinted, verified and transmitted; a rotation after verification produces a different fingerprint and forces re-verification | `...::F07CredentialSnapshotTests` (2 tests) |
| N02 | Medium | The discovery regression exercised the generic `call()` path, not the typed discovery entry point | Yes — the old test named the generic path | The typed entry point `list_workflows_typed()` is now exercised for both the identity guard and the grant ceiling | `...::N02TypedDiscoveryTests` (2 tests) |
| N05 | Medium | The constructor bounded unique ids but not inspected entries (13,192 duplicates fully consumed) and accepted a 1,000,000-character restored id | Yes — both probes reproduced | The checkpoint is bounded on **inspected entries** (`MAX_RESTORED_ENTRIES`) as well as unique ids, and a restored id must be bounded and well-formed: oversized or control-carrying ids are refused rather than silently dropped | `...::N05CheckpointBoundTests` (5 tests) |
| N06 | Medium | An uncached identity verification could issue an HTTP request before the reservation, and the ceiling's scope was undefined for that traffic | Yes — the ordering was visible in the source | The scope is now **defined and documented**: `max_calls` bounds repository operations, and identity and ownership verification are authorization traffic with their own bounded caches (one identity request per verified (token, account) pair, one ownership lookup per verified (workflow, run) pair). The claim "before any transport exists" is removed from the code and the docs | `...::N06CeilingScopeTests` (2 tests) |
| N11 | Medium (new) | One shared write-body contract used GitHub field names, so a legitimate GitLab merge request (`source_branch`/`target_branch`) was refused as an unknown key | Yes — the old test asserted the rejection as if it were correct coverage | Each provider has its **own** contract table (`GITHUB_WRITE_BODY_CONTRACTS`, `GITLAB_WRITE_BODY_CONTRACTS`) with its official field names, its own mandatory references, and positive as well as negative tests | `...::N11ProviderContractTests` (4 tests) |
| F20 | Informational | The package pinned `176034a` while the candidate carried subsequent production code; ancestry is not code-tree equivalence | Yes — the pin lagged by seven commits | The pin contract now requires the pinned tree to equal HEAD's tree, so a documents-only re-pin passes and a production-code commit that is not re-pinned fails | `...::F20RevisionBindingTests` and `tests/test_rereview_regressions.py::F20Tests` |
| N10 | Medium | Several closures rested on tests that did not exercise the full invariant | Yes — each named deficiency was checked against its test | Every closure in this section now rests on a **behavioural** test that drives the production entry point (the provider `call()`, the typed discovery method, the polling constructor, the consent store's own retention) and fails against the vulnerable implementation. The deficiencies the reviewer named — manual SQL instead of the retention API, the generic discovery path, untested duplicates and oversized ids, a disabled credential channel, a declared workflow rather than the run's own, omitted reference fields, and ancestry rather than equivalence — are each closed by a test that would fail before the fix | `tests/test_review4_regressions.py` (30 tests) |

**Recovered historical findings:** F06 (worker-scope spoofing) and F20 (evidence
pinned to the wrong commit) are recorded as recovered substance, not verbatim
quotations. The recovered F06 reproducer is asserted denied in
`tests/test_rereview_regressions.py::F06Tests`; the F20 contract above is the
revised evidence pin. Both remain marked *re-confirm* pending the original
reviewer's canonical text.

**Scope of this remediation, stated honestly:** every fix is source-level and
unit-tested against test-owned transports. No live provider, GitHub token or
host shell was used. The reviewer's isolated probes were reproduced first, so
each fix is anchored to an observed defect rather than to a reading. The
reviewer's own execution limitation could not be closed from this repository:
an independent clone and full-suite reproduction remain the reviewer's gate,
and this section does not claim them.

**Next step:** push the exact head, verify its CI, re-pin the review package,
and request a fourth independent review against it.

## 3-E. Gate 1 fourth review of `10176308733e1dd9940560bcec259b43e738a500` (25 November 2026) — FAIL / DO NOT APPROVE

The reviewer states it reviews the **requested revision** rather than the newer
PR head, and that the current head differs from it only under `docs/` and
`harness/`. It retrieved the metadata of all four supplied CI runs, compared
their revisions, and retrieved the actual validation job log: **757 reported,
756 passed, 1 skipped** (`test_doctor.OverallPrecedenceTests.test_all_ok_reads_ok`,
skipped because the CI host had a genuinely failing doctor check). It states a
maintainer CI run is not a security acceptance, and that the CI checkout was a
PR merge commit rather than a detached checkout of the candidate.

Its execution limitation is recorded verbatim in substance: a clone failed with
`Could not resolve host: github.com`, so it retrieved the requested revision's
source and recursive tree through the GitHub connection and executed isolated
probes from transcribed excerpts. Every requested command is recorded HOLD.

Its architectural framing is the contract this remediation implements:
authorization must be bound to the **exact credential, resource and immutable
request that ultimately reaches the transport**, and that invariant is fixed
centrally rather than per manifestation.

| # | Severity | Finding (as reported) | Reproduced? | Remediation | Named regression tests |
|---|---|---|---|---|---|
| F07 / N02 | High | The generic `call()` path took one credential snapshot, but `list_workflows_typed()` read the credential twice (`_require_account_identity(grant, self._token_value())` then `_exchange(..., self._token_value())`); the reviewer's probe verified `first` and transmitted `rotated` | Yes — the two read sites were visible and a probe confirmed the divergence | Both entry points now read the credential **once** and transmit that exact snapshot. The proof is asserted against the **authorization header a test-owned HTTP opener sees**, not against an injected transport that reads the environment itself (the reviewer's own critique of the previous test) | `tests/test_review5_regressions.py::F07CredentialSnapshotTests` (3 tests) |
| N07 | High | The ownership cache key `(workflow, run_id)` omitted repository, granted reference, verified account and credential identity; the reviewer's probe showed a second authorization for `develop` served from the `main` lookup; GitLab derived the reference from caller slots with an empty-string fallback | Yes — the cache key and the slot-derived reference were both confirmed | The memo is keyed by the **complete authorization context** (provider, repository, **granted** reference, account, credential fingerprint, workflow, run id), the reference comes from the grant rather than the slots, evidence expires after a bounded window, lookups run under one lock so concurrent requests coalesce, and the lookup is charged against an authorization budget | `...::N07OwnershipContextTests` (6 tests: cross-repository, cross-reference, credential rotation, grant-bound reference, empty caller slot) |
| N06 | Medium | A bounded cache bounds stored entries, not authorization requests; rejected authorization is neither cached nor charged; concurrent ownership lookups could repeat; the `_reserve_call` docstrings still claimed "before any transport is built" | Yes — the docstrings still carried the old claim and no request budget existed | `_charge_authorization_request()` bounds authorization traffic **as requests** in both providers; the docstrings now state precisely that `max_calls` bounds repository operations and authorization traffic is separately bounded; ownership lookups coalesce under one lock | `...::N06AuthorizationTrafficTests` (2 tests, incl. the ceiling and 6-thread coalescing) |
| N12 | High (new) | Both providers validated the caller's mutable body, authorized, then transmitted that same body: a mutation during authorization would diverge from what was checked | Yes — the control flow was confirmed and a hostile-mutation probe is now a regression test | The validated body is copied into a bounded immutable snapshot **before** any authorization request, and that exact snapshot is wire-encoded and transmitted; a caller mutating the original mapping cannot change what is sent | `...::N12BodySnapshotTests` (2 tests, incl. the mutation-during-verification case) |
| N13 | High (new) | `merge_pull` was addressed by numeric id with no check that the pull request targets the granted reference | Yes — no target verification existed in the inspected source | The merge is preceded by a trusted-metadata lookup of the pull/merge request's own target reference; a mismatch refuses `reference_not_granted` before the merge exchange, and missing metadata refuses `merge_target_unavailable` | `...::N13MergeTargetTests` (4 tests, both providers) |
| N14 | High (new) | GitLab `rerun_workflow` verified a pipeline's ownership and then addressed `/pipeline_schedules/{workflow}/play`: the resource checked was not the resource acted upon | Yes — the path and the preceding ownership check were both confirmed | A rerun retries the **verified pipeline** (`/pipelines/{id}/retry`). Schedule configuration is a resource no ownership check can verify here, so `configure_workflow` refuses `resource_not_verifiable` rather than acting on an unchecked target | `...::N14ResourceMismatchTests` (2 tests) |
| N05 | Medium | Duplicate and oversized cases were fixed, but malformed entries were silently skipped: `[None, 123, "", "   "]` was accepted and `"   "` retained | Yes — the probe reproduced exactly that | One validator (`event_id`) is used across restoration, normalization and acceptance: non-string, empty, whitespace-only, oversized and control-carrying ids all refuse rather than being skipped | `...::N05StrictValidationTests` (4 tests) |
| F20 | Informational | The frozen candidate's package still pinned `9b6ce534`, and the net-tree `git diff` does not prove every intervening commit was documentation-only | Yes — the reviewer compared the frozen package against the candidate | The pin is re-pinned to this remediation head, and the negative-history requirement is met with **fixtures in temporary git repositories**: a documentation-only intervening change passes the documented contract and a production-code one fails it | `...::F20RevisionContractTests` (3 tests, incl. both fixtures) |
| N10 | Medium | The previous rotation test never rotated during the request, used a transport that receives no credential, and read the environment itself | Yes — that exact critique was confirmed | Every closure in this section drives the production boundary — the authorization header a test-owned opener sees, the polling constructor, git history in temporary repositories, a body mutated inside an authorization callback — and each test fails against the vulnerable implementation | `tests/test_review5_regressions.py` (25 tests) |

**Accepted without change by this remediation:** F03, F06, F12, F14, F15, F17,
N01, N03, N04, N09 (static closures and retained acceptances), plus the
accepted parts of N08 (mandatory reference checks, PR destination binding,
branch-source sha verification) and N11 (provider-specific contracts).

**Scope of this remediation, stated honestly:** every fix is source-level and
unit-tested against test-owned transports and a test-owned HTTP opener. No live
provider, GitHub token or host shell was used. The reviewer's execution
limitation could not be closed from this repository: an independent clone and
full-suite reproduction remain the reviewer's gate, and this section does not
claim them. The environmental and live acceptance HOLDs (host-level process
authentication, OS confinement, live provider/GitHub behaviour, clean-machine
acceptance) are unchanged and are not converted into source-level closures.

**Next step:** push the exact head, verify its CI, re-pin the review package,
and request a fifth independent review against it.

## 3-F. Fifth review remediation progress (25 November 2026) — baseline stabilized

After the fifth independent review returned **FAIL / DO NOT APPROVE** with 6 high-severity findings still open (N07, N12, N13, N15, plus N06/N11/N17 partial), the codebase was restored to the fifth-review baseline (`892d14c`) and the following remediation was completed:

### Completed fixes (tests passing)

| Finding | Fix | Verification |
|---------|-----|--------------|
| **N05** (polling validation) | Raw event ID/type validated BEFORE coercion; single strict validator `event_id()` used across restore/normalize/accept | 14/14 polling tests pass; all N05 checkpoint tests pass |
| **N16** (accept pre-flight) | `accept()` performs full shape + ID + allowlist validation on ALL events BEFORE any `_seen` mutation; atomic batch rejection | 14/14 polling tests pass; new N16 tests pass |
| **Polling idempotency** | `normalize()` filters already-seen events for backward compatibility | `test_polling_does_not_replay_evicted_event_ids` passes |

All **788 tests pass** (was 788 at fifth review baseline).

### Remaining high-severity findings (for sixth review)

| # | Finding | Required fix |
|---|---------|--------------|
| **N07** | GitHub: `head_branch` not validated against grant reference; GitLab: workflow relationship not established | In `_require_run_of_workflow`/`_require_run_of_reference`, check `head_branch` / workflow membership |
| **N12** | Branch-source check uses original `body`/`payload`, not validated snapshot | Materialize snapshot BEFORE validation; pass snapshot to `_require_branch_source` |
| **N13** | Merge target cached for 300s; survives PR retargeting | Remove cache for merge targets; revalidate on every request |
| **N15** | `check_call`/`validated_slots` re-reads caller mapping after authorization | Use `_payload_get()` for all slot access (already in scope.py); ensure no re-read after materialization |
| **N06** | `_require_branch_source` lookup not charged to auth budget | Call `_charge_authorization_request()` in branch-source verification |
| **N17** | `_wire_body` treats all tuples as mappings, corrupts JSON arrays | Preserve array/object distinction in snapshot→wire conversion |
| **N11** | Provider contracts support arrays but `_wire_body` corrupts them | Same as N17 fix |

### Architectural recommendation (from fifth review)

> Consolidate corrections into one shared request preparation and authorization mechanism. The connector should: materialize request once → validate snapshot → authorize snapshot → transmit snapshot. No return to caller-owned objects after materialization. Centralized authorization budget. For mutable remote resources, revalidate or refuse.

### Next step

Request sixth independent review against current head. PR #14 remains draft.


## Sixth-review remediation candidate (2026-11-26)

This is a development successor, not an independent PASS. The frozen sixth
review candidate `785a60a` and PR #14 are preserved. The supplied green CI
45683837558 was for the newer head `7dabbdc`; CI 45683303692 on the sixth
candidate's merge checkout failed three F20 checks.

Implemented in the separate branch `p1/gate1-review6-remediation`:

- N12/N15/N17/N11: one bounded private typed materialization for connector
  mappings, with immutable objects/arrays distinguished and branch-source
  authorization and response checking restricted to prepared values.
- N06: charge GitHub branch-source authorization lookups before exchange.
- N07: require GitHub run metadata to match the granted branch; deny GitLab
  pipeline operations when named workflow membership cannot be established.
  Historical positive fixtures for GitLab branch-only authorization now
  explicitly exercise the stricter refusal policy. This deliberately restricts
  those pipeline operations; it does not claim live GitLab compatibility.
- N13: remove mutable merge-target authorization caching. The remote race
  between metadata lookup and merge remains unresolved; no strict
  target-atomic merge guarantee is claimed.
- N18: preflight distinct fresh IDs and available capacity under a lock;
  accept consumes the input batch once; consolidate duplicate polling validators.
- F20: shared ancestry/per-commit path verifier, rejecting nonlinear history
  in the docs-only exception. CI checks out the exact PR head with full history
  and no persisted checkout credentials.
- Add focused negative regression cases. No fail-before/success-after matrix
  or independent full-suite execution is claimed yet (N10 remains open).

Code pin: `67c475e0c62cae2dc38ee13deceb1385c5f06635`. Candidate CI and independent
acceptance remain pending. Host authentication, OS confinement, live provider
behavior and clean-machine acceptance remain HOLD. No merge or release.
