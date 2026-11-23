# TIHULU Boru Yolu — Security review package (Gate 1)

Prepared for an independent reviewer. Every claim below is either a command you
can run or a file/test you can read; nothing is asserted without a pointer.

- Repository: https://github.com/Tihulu/Tihulu-Boru-Yolu
- Branch under review: `p1/boru-core-vertical-slice`
- Code head under review: `176034a1039dceef166e47f40a3cd10e64e36dec`
  (the head this package describes; a later documents-only commit moves the head
  without changing the code tree — `tests/test_rereview_regressions.py` asserts
  the pin is HEAD or an ancestor of it)
- Pull request: https://github.com/Tihulu/Tihulu-Boru-Yolu/pull/14 (draft, not merged)
- CI (this head, success): https://github.com/Tihulu/Tihulu-Boru-Yolu/actions/runs/45269296922
- Issue tracker: https://github.com/Tihulu/Tihulu-Boru-Yolu/issues
- Ledger: [harness/build-log.md](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/harness/build-log.md)

Baseline: the branch is based on `plan/architecture-security-profiles-ubuntu-popos`
(draft PR #1), not `main`.

## 1. How to reproduce (commands)

Run from a clone of the branch:

~~~bash
git clone https://github.com/Tihulu/Tihulu-Boru-Yolu.git
cd Tihulu-Boru-Yolu
git checkout p1/boru-core-vertical-slice
python3 scripts/check_project.py     # expected: PASS (30 documents + sample policy invariants)
python3 -m unittest discover -s tests   # expected: Ran 701 tests ... OK
PYTHONPATH=. python3 tests/test_review_regressions.py   # expected: Ran 20 tests ... OK
python3 scripts/evidence.py          # expected: exit 0, overall all-PASS
python3 -m boru doctor --state-dir local-state   # expected: overall: ok, live_acceptance: HOLD
python3 -m boru demo                 # expected: state REVIEW, evidence_class simulated
~~~

Observed result on the head commit: **PASS / 701 tests / exit 0** (local run of
`check_project.py`, the full suite, `scripts/evidence.py`, `boru doctor` and
`boru demo`); the same suite passed in CI on this head (run 45048886502). If any
of these fail on your run, that is a finding.

## 2. What to review, in order

| # | Component | File(s) | Link |
|---|---|---|---|
| 1 | Worker identity registry | `boru/workers.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/workers.py) |
| 2 | Authorization broker | `boru/broker.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/broker.py) |
| 3 | Authenticated loopback surface | `boru/broker_service.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/broker_service.py) |
| 4 | Bounded read-only worker | `boru/executor.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/executor.py) |
| 5 | Disclosure gate | `boru/privacy.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/privacy.py) |
| 6 | Consent store (persistent) | `boru/consent.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/consent.py) |
| 7 | End-to-end pipeline | `boru/pipeline.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/pipeline.py) |
| 8 | Rejection ledger | `boru/audit.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/audit.py) |
| 9 | Cross-boundary tracer | `boru/boundary.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/boundary.py) |
| 10 | Request scope (connectors) | `boru/connectors/scope.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/connectors/scope.py) |
| 11 | GitHub connector | `boru/connectors/github.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/connectors/github.py) |
| 12 | GitLab connector | `boru/connectors/gitlab.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/connectors/gitlab.py) |
| 13 | Workflows / dispatch inputs | `boru/connectors/workflows.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/connectors/workflows.py) |
| 14 | Polling sync (no listener) | `boru/connectors/polling.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/connectors/polling.py) |
| 15 | Sandbox grant contract | `boru/sandbox.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/sandbox.py) |
| 16 | Core policy axes | `boru/policy.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/policy.py) |
| 17 | Typed contracts | `boru/types.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/types.py) |
| 18 | Orchestrator | `boru/core.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/core.py) |
| 19 | Durable state store | `boru/store.py` | [link](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/boru/store.py) |

## 3. Invariant checklist (each with its test)

### Policy and contracts
- [ ] Four axes (optimization/inference/execution/disclosure) are independent; a mode change cannot widen another axis — [test_policy.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_policy.py) (`test_optimization_change_never_touches_other_axes`), [test_typed_contracts.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_typed_contracts.py) (`test_policy_and_contract_defaults_agree`).
- [ ] `LOCAL_ONLY` forbids any cloud fallback — `test_local_only_forbids_cloud_fallback`.
- [ ] Unknown enum values, non-boolean flags and out-of-range limits are rejected — `test_invalid_policy_rejected_at_construction`.
- [ ] Task/result contracts reject unknown fields and private-carrying keys (`raw_stdout`, `environment`, `api_key`, `home_path`, ...) — `test_typed_contracts.py` (`test_private_payload_fields_rejected`, `test_typed_result_rejects_private_fields`).
- [ ] A child task can never override its parent's policy axes or budgets — `test_manual_requires_selection_and_child_keeps_axes`.

### Dispatch and budgets
- [ ] A completed reply reaches `REVIEW`; `DONE` requires an explicit owner review and preserves `evidence_class` — [test_core.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_core.py) (`test_full_pipeline_with_mock`), [test_store.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_store.py) (`test_review_cannot_promote_evidence_class`).
- [ ] A forged/mismatched provider or model reply becomes `FAILED` — `test_forged_reply_never_becomes_done`.
- [ ] Expired deadline and over-ceiling budget hold with **zero** provider calls — `test_ceiling_over_estimate_holds_without_a_call`, `test_cost_ceiling_refuses_an_unbounded_spend`, `test_reported_usage_over_ceiling_holds_after_the_call`.
- [ ] A task-level model selection binds the dispatch in every mode; an unpermitted selection is refused — [test_router.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_router.py) (`test_selection_is_honored_in_auto_mode`), [test_boundary.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_boundary.py).
- [ ] Interrupted `RUNNING`/`VERIFYING` tasks return to `HOLD` on restart with no dispatch replay — `test_interrupted_running_task_recovers_to_hold`.
- [ ] Capability tags must all match (no partial acceptance) — `test_capability_tags_filter`.
- [ ] The recorded evidence class comes from provider provenance; a provider's own claim cannot upgrade it — `test_review_regressions.py` (`test_mock_provider_cannot_claim_direct_evidence`).
- [ ] The outbound boundary classification is derived from the payload that is actually sent — `test_boundary.py`, `test_review_regressions.py`.

### Worker identity, broker, surface
- [ ] Identity secrets are 256-bit, stored owner-only (0600), bounded, revocable and expiring; `valid()` is constant-time — [test_workers.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_workers.py) (`test_secrets_are_256_bit_and_never_returned`, `test_expiry_enforced`, `test_create_validate_revoke`).
- [ ] Revocation and expiry persist across a restart — `test_persistence_across_restart`.
- [ ] Group/world-writable directories, symlinked files/paths and malformed records are refused — `test_group_writable_directory_rejected`, `test_symlinked_worker_file_rejected`, `test_bad_worker_file_rejected`.
- [ ] Broker denies: unknown operation, undeclared resource, worker without scope, missing/expired/revoked grant, replayed nonce, malformed request, missing consent store — [test_broker.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_broker.py) (`test_missing_grant_is_denied`, `test_expired_grant_is_denied`, `test_revoked_grant_is_denied`, `test_replayed_nonce_is_denied`, `test_malformed_requests_are_denied`, `test_broker_requires_a_consent_store`).
- [ ] Resource aliases cannot traverse (`..`) or be symlinks — `test_scope_allowlist_rejects_escapes`, `test_symlinked_alias_rejected`.
- [ ] A receipt names its resource only by an opaque token, never a path or the alias itself, and a borrow or a key mismatch refuses — `test_broker.py` (`test_allowed_request_issues_a_receipt`), `test_executor.py` (`test_a_borrowed_receipt_fails_under_a_foreign_key`, `test_a_swapped_target_invalidates_the_receipt`).
- [ ] A worker refuses fields the receipt does not name, and a forged operation fails verification — `test_executor.py` (`test_worker_refuses_fields_beyond_the_receipt`, `test_forged_receipt_is_refused`).
- [ ] The request worker can never widen the broker's own worker identity — `test_review_regressions.py` (`test_broker_rejects_attacker_supplied_worker_scope`).
- [ ] The surface is loopback-only, one request per connection, bounded, idle-timed; a wrong secret or unknown worker denies before authorization — [test_broker_service.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_broker_service.py) (`test_public_bind_is_refused`, `test_wrong_secret_is_denied`, `test_unknown_worker_is_denied`, `test_revoked_worker_is_denied`).
- [ ] The end-to-end pipeline authorizes over that authenticated surface; a denial precedes any acquisition — [test_pipeline.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_pipeline.py) (`test_wrong_secret_is_denied_over_the_socket`, `test_revoked_worker_is_denied_over_the_socket`).

### Worker output and disclosure
- [ ] `list_dir_alias` returns a count, never names; `read_file_alias` returns metadata, never content; requesting `content`/`raw_stdout`/`file_contents` is refused — [test_executor.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_executor.py) (`test_content_is_never_produced`, `test_list_returns_a_count_not_names`).
- [ ] Aliases are opened with `O_DIRECTORY|O_NOFOLLOW` — `test_symlinked_alias_is_refused`, `test_missing_alias_directory_is_refused`.
- [ ] L0/L1/L2 field allowlists are enforced; L2 under `MINIMUM_NECESSARY` is refused before touching the resource — [test_privacy.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_privacy.py) (`test_l2_requires_scoped_approval_and_a_grant`).
- [ ] Consent grants bind recipient/task/field/**alias**/**level**/expiry/nonce; replay, revocation and same-id re-issue deny; an L0 grant never authorizes L2 (both stores) — `test_consent_store.py` (`test_grant_is_bound_to_its_alias_and_level`, `test_grant_id_is_immutable_once_issued`), `test_privacy.py`, `test_review_regressions.py` (`test_l0_owner_grant_cannot_authorize_l2_local`, `test_l0_owner_grant_cannot_authorize_l2_persistent`).
- [ ] The rejection ledger is append-only, bounded and sanitized (no payload, path, token or provider text) — [test_audit.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_audit.py) (`test_entries_never_carry_payloads_or_paths`, `test_retention_prunes_the_oldest_rows_only`).

### Connectors
- [ ] Repository/reference binding, no `method`/`path` overrides, per-slot charset validation, account-wide listing denied — [test_connector_scope.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connector_scope.py) (`test_path_override_is_refused`, `test_method_override_is_refused`, `test_other_repository_is_refused_without_a_request`, `test_account_wide_listing_is_refused_with_a_repository_grant`).
- [ ] Redirects are never followed; content type validated; body bounded; `read_file` response reference verified — [test_connector_scope.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connector_scope.py) (`test_redirect_is_refused_and_never_followed`, `test_unexpected_content_type_is_refused`, `test_response_reference_mismatch_is_denied`).
- [ ] Workflow operations bind to a grant allowlist — `test_undeclared_workflow_is_denied_without_a_request`.
- [ ] Token/account identity is verified against the grant account before any repository request, and the audit event carries no repository route — `test_connectors.py` (`test_identity_mismatch_denies_before_any_repository_call`), `test_review_regressions.py` (`test_github_call_must_enforce_account_identity`, `test_connector_audit_does_not_record_repository_paths`).
- [ ] The `?ref=` query uses exactly the validated reference; a rerun without a granted workflow name makes no request; a dispatch body cannot override the granted reference — `test_review_regressions.py` (`test_github_read_file_must_use_granted_reference`, `test_gitlab_read_file_must_use_granted_reference`, `test_workflow_rerun_cannot_ignore_workflow_allowlist`, `test_workflow_dispatch_cannot_override_reference_in_body`).
- [ ] Repository slots reject NUL and other control characters — `test_review_regressions.py` (`test_repository_slots_reject_nul`).
- [ ] Dispatch inputs validated before any dispatch; an undeclared schema is refused — [test_workflows.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_workflows.py).
- [ ] Polling sync is listener-free; allowlist bounded; idempotent across restarts; an evicted id is never replayed — `test_polling.py` (`test_no_listener_is_created`, `test_history_never_forgets_an_evicted_id`), `test_review_regressions.py` (`test_polling_does_not_replay_evicted_event_ids`).
- [ ] A denied operation produces **no** outbound request — [test_connectors.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connectors.py) (`test_denied_operations_make_no_request`).

### Sandbox contract
- [ ] Decisions only; nothing executes; host Shell is absent from the allowlist — [test_sandbox.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_sandbox.py) (`test_host_operations_are_absent`).

## 3-A. First review findings and their remediation

The first review of `cc73940` returned **FAIL** with findings F01–F22. Every
finding recorded in the working notes is remediated on this head — see
`docs/REVIEW_FINDINGS.md` for the per-finding table, which also records the two
findings (F06 and F20) whose canonical text the working notes do not carry and
which are marked *to re-confirm* rather than described from memory. The
reviewer's own 20 regression probes are checked in at
`tests/test_review_regressions.py` so CI runs the same executable acceptance
spec (20/20 pass). Re-review must confirm each row and re-issue the canonical
finding text for F06 and F20.

| # | Finding (short) | Remediation | Commit |
|---|---|---|---|
| F01 | An executor receipt was never verified | `boru/authorization.py`: HMAC-signed, request-bound receipts (task, operation, resource token, worker, grant, nonce, expiry, fields, target); `boru/executor.py` verifies every receipt under the worker authorization key before any filesystem access and refuses tampered, borrowed or expired receipts | `e449d17` |
| F02/F13 | Worker id traversal; nonfinite timestamps | `boru/workers.py`: an id is one opaque segment (no separator, parent reference or drive letter); a nonfinite stamp can no longer issue a usable identity — the record is created and refused at every `valid()` check | `e449d17`, `8e0869b` |
| F03/F11 | Consent not bound to alias/level/field | `boru/consent.py`, `boru/privacy.py`: grants bind recipient, task, operation, alias, field and level; a weaker grant never covers a wider level; a grant for one resource never serves another | `e449d17`, `8e0869b` |
| F08 | Alias traversal followed links | `boru/executor.py`: the alias root is opened with `O_DIRECTORY|O_NOFOLLOW` and a target is resolved component-wise with `dir_fd` + `O_NOFOLLOW`, so no symlink or parent reference can escape | `e449d17` |
| F09 | Ledger stored unsanitized subjects | `boru/audit.py`: stored identifiers are sanitized (a path, URL or token fragment keeps no separator that could make it a filesystem or network reference); empty or oversized values are refused | `e449d17`, `8e0869b` |
| F12 | A revoked grant id could be re-issued | `boru/consent.py`, `boru/privacy.py`: a grant id is immutable once issued; re-issue is refused | `8e0869b` |
| F14 | Unbounded service concurrency | `boru/broker_service.py`: a bounded semaphore; beyond the bound the surface denies `service_busy` | `e449d17` |
| F16 | Polling replayed evicted ids | `boru/connectors/polling.py`: the seen registry is bounded and never forgets; a full registry refuses new work | `93fb0de` |
| F17 | Unbounded nonce retention | `boru/consent.py`, `boru/broker.py`: used nonces are pruned to a documented bound | `e449d17` |
| F18 | Read metadata was synthesized | `boru/executor.py`: real, bounded `size`/`line_count` from `fstat` and bounded reads; content never retained | `e449d17` |
| F10 | Nested private fields validated; results saved before verification | `boru/types.py`: recursive bounded payload validation (a private field nested inside an innocent key does not launder it); `boru/core.py`: a failed verification is never persisted as a result | `93fb0de` |
| F04 | Two parses of one repository reference | `boru/connectors/scope.py`: `check_call` returns the validated slots; both providers build their official path from exactly those slots | `93fb0de` |
| F05/F51 | Dispatch body and workflow not bound | `boru/connectors/scope.py`: a dispatch body is validated before any transport (its `ref` must be the granted reference, inputs bounded); `rerun`/`configure`/`dispatch` require a granted workflow name | `93fb0de` |
| F07 | Account identity optional in `call()` | `boru/connectors/github.py`, `gitlab.py`: `call()` verifies the account behind the token once per provider and refuses a mismatch before any repository request | `93fb0de` |
| F15/F49/F50 | Unbounded response/error bodies | `boru/connectors/github.py`, `gitlab.py`: responses are capped, error bodies keep only a bounded prefix, content type is validated | `93fb0de` |
| F19 | Sizing limits had no upper bound | `boru/policy.py`: `max_result_fields` 1..32, `max_retries` 0..8 | `93fb0de` |
| F21/F22 | Evidence class came from a provider claim; boundary class was asserted | `boru/core.py`: the recorded evidence class is derived from provider provenance (a mock never claims `direct`), a reply's own claim is not trusted, the outbound classification is derived from the payload actually sent, and the classified messages are the ones transmitted | `93fb0de` |

Not changed (recorded as HOLD, not fixed): host-level process authentication,
OS confinement, live provider/GitHub behaviour and clean-machine acceptance.

## 4. Explicitly out of scope for this review

Host-level process authentication, OS confinement, sandbox runtime, live
provider/GitHub behaviour and clean-machine acceptance are separate gates
(`docs/OWNER_GATE_GUIDE.md`).

## 5. Live evidence already recorded

| Gate | Evidence | Link |
|---|---|---|
| A21 — Boru Core → direct Jan, 3 conversations | provider/model/usage recorded, owner review to DONE, non-allowlisted model refused with no call | [ledger entry](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/harness/build-log.md) |
| A23 — real OpenCode child session | session/message IDs, agent, model, provider; sessions deleted | [ledger entry](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/harness/build-log.md) |

## 6. Findings template

| # | Severity | Component | Finding | Reproducing test / input | Suggested fix |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |

## 7. PASS criteria

1. No unresolved critical or high finding.
2. Every medium finding fixed or explicitly accepted by the owner.
3. Reviewer name, date and reviewed commit recorded in `harness/build-log.md`.

**Current status: HOLD — a re-review of `1617709` returned FAIL/DO NOT
APPROVE (findings F03, F06, F07, F12, F14, F15, F17, F20 and N01–N05, see
`docs/REVIEW_FINDINGS.md` section 3-B). Every one of them has been remediated
on this head (`176034a103`) with a named negative regression test in
`tests/test_rereview_regressions.py`; an independent re-review of the resulting
tree is still required before Gate 1 can pass, and the reviewer's own verdict is
the only authority on closure.**
