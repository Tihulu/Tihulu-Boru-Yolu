# TIHULU Boru Yolu — Security review package (Gate 1)

Prepared for an independent reviewer. Every claim below is either a command you
can run or a file/test you can read; nothing is asserted without a pointer.

- Repository: https://github.com/Tihulu/Tihulu-Boru-Yolu
- Branch under review: `p1/boru-core-vertical-slice`
- Head commit: `0cfe40786c8592f4fbf57fec797382e409fd077d`
- Pull request: https://github.com/Tihulu/Tihulu-Boru-Yolu/pull/14 (draft, not merged)
- CI (this head, success): https://github.com/Tihulu/Tihulu-Boru-Yolu/actions/runs/44931288098
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
python3 scripts/check_project.py     # expected: PASS (25 documents + sample policy invariants)
python3 -m unittest discover -s tests   # expected: Ran 556 tests ... OK
python3 scripts/evidence.py          # expected: exit 0, overall all-PASS
python3 -m boru doctor --state-dir local-state   # expected: overall: ok, live_acceptance: HOLD
python3 -m boru demo                 # expected: state REVIEW, evidence_class simulated
~~~

Observed result on the head commit: **PASS / 556 tests / exit 0 / CI success**.
If any of these fail on your run, that is a finding.

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

### Worker identity, broker, surface
- [ ] Identity secrets are 256-bit, stored owner-only (0600), bounded, revocable and expiring; `valid()` is constant-time — [test_workers.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_workers.py) (`test_secrets_are_256_bit_and_never_returned`, `test_expiry_enforced`, `test_create_validate_revoke`).
- [ ] Revocation and expiry persist across a restart — `test_persistence_across_restart`.
- [ ] Group/world-writable directories, symlinked files/paths and malformed records are refused — `test_group_writable_directory_rejected`, `test_symlinked_worker_file_rejected`, `test_bad_worker_file_rejected`.
- [ ] Broker denies: unknown operation, undeclared resource, worker without scope, missing/expired/revoked grant, replayed nonce, malformed request, missing consent store — [test_broker.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_broker.py) (`test_missing_grant_is_denied`, `test_expired_grant_is_denied`, `test_revoked_grant_is_denied`, `test_replayed_nonce_is_denied`, `test_malformed_requests_are_denied`, `test_broker_requires_a_consent_store`).
- [ ] Resource aliases cannot traverse (`..`) or be symlinks — `test_scope_allowlist_rejects_escapes`, `test_symlinked_alias_rejected`.
- [ ] A receipt never carries a real path — `test_receipt_never_carries_a_real_path`.
- [ ] The surface is loopback-only, one request per connection, bounded, idle-timed; a wrong secret or unknown worker denies before authorization — [test_broker_service.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_broker_service.py) (`test_public_bind_is_refused`, `test_wrong_secret_is_denied`, `test_unknown_worker_is_denied`, `test_revoked_worker_is_denied`).
- [ ] The end-to-end pipeline authorizes over that authenticated surface; a denial precedes any acquisition — [test_pipeline.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_pipeline.py) (`test_wrong_secret_is_denied_over_the_socket`, `test_revoked_worker_is_denied_over_the_socket`).

### Worker output and disclosure
- [ ] `list_dir_alias` returns a count, never names; `read_file_alias` returns metadata, never content; requesting `content`/`raw_stdout`/`file_contents` is refused — [test_executor.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_executor.py) (`test_content_is_never_produced`, `test_list_returns_a_count_not_names`).
- [ ] Aliases are opened with `O_DIRECTORY|O_NOFOLLOW` — `test_symlinked_alias_is_refused`, `test_missing_alias_directory_is_refused`.
- [ ] L0/L1/L2 field allowlists are enforced; L2 under `MINIMUM_NECESSARY` is refused before touching the resource — [test_privacy.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_privacy.py) (`test_l2_requires_scoped_approval_and_a_grant`).
- [ ] Consent grants bind recipient/task/field/expiry/nonce; replay and revocation deny — [test_consent_store.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_consent_store.py).
- [ ] The rejection ledger is append-only, bounded and sanitized (no payload, path, token or provider text) — [test_audit.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_audit.py) (`test_entries_never_carry_payloads_or_paths`, `test_retention_prunes_the_oldest_rows_only`).

### Connectors
- [ ] Repository/reference binding, no `method`/`path` overrides, per-slot charset validation, account-wide listing denied — [test_connector_scope.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connector_scope.py) (`test_path_override_is_refused`, `test_method_override_is_refused`, `test_other_repository_is_refused_without_a_request`, `test_account_wide_listing_is_refused_with_a_repository_grant`).
- [ ] Redirects are never followed; content type validated; body bounded; `read_file` response reference verified — [test_connector_scope.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connector_scope.py) (`test_redirect_is_refused_and_never_followed`, `test_unexpected_content_type_is_refused`, `test_response_reference_mismatch_is_denied`).
- [ ] Workflow operations bind to a grant allowlist — `test_undeclared_workflow_is_denied_without_a_request`.
- [ ] Token/account identity is verified against the grant account — `test_connector_scope.py` (`test_mismatched_identity_is_refused`).
- [ ] Dispatch inputs validated before any dispatch; an undeclared schema is refused — [test_workflows.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_workflows.py).
- [ ] Polling sync is listener-free; allowlist bounded; idempotent across restarts — [test_polling.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_polling.py) (`test_no_listener_is_created`).
- [ ] A denied operation produces **no** outbound request — [test_connectors.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_connectors.py) (`test_denied_operations_make_no_request`).

### Sandbox contract
- [ ] Decisions only; nothing executes; host Shell is absent from the allowlist — [test_sandbox.py](https://github.com/Tihulu/Tihulu-Boru-Yolu/blob/p1/boru-core-vertical-slice/tests/test_sandbox.py) (`test_host_operations_are_absent`).

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

**Current status: HOLD — no independent review has been performed.**
