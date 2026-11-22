# Re-review request — Gate 1 (previous verdict: FAIL, findings F01–F22)

Ready-to-send request for the independent reviewer of the first Gate 1 review.
The repository never records a verdict the reviewer has not given: this file
prepares the ask, it does not claim a PASS.

Re-review request — TIHULU Boru Yolu, Gate 1 (previous verdict: FAIL, findings F01-F22)

Repository: https://github.com/Tihulu/Tihulu-Boru-Yolu
Branch: `p1/boru-core-vertical-slice` (draft PR #14)
Code head under review: the head recorded in `docs/REVIEW_PACKAGE.md`
(currently `87d75d91fa562729f0516e994a9a15ad965fe393`; a later
documents-only commit does not change the code tree).

What changed since your review of cc73940:
- Every finding F01-F22 is remediated; the per-finding table with the closing
  commit is in docs/REVIEW_PACKAGE.md section 3-A.
- Your 20 regression probes are now checked in as
  tests/test_review_regressions.py and run inside the suite: 20/20 pass
  (only the PolicyViolation import was added; assertions are unchanged).

Please run, from a clone of the branch (no host install, no network, no
credentials, no sandbox runtime):
  python3 scripts/check_project.py
  python3 -m unittest discover -s tests      # 663 tests ... OK
  PYTHONPATH=. python3 tests/test_review_regressions.py
  python3 scripts/evidence.py                # exit 0
  python3 -m boru doctor --state-dir local-state
  python3 -m boru demo

Review focus (unchanged scope in docs/REVIEW_PACKAGE.md):
1. The broker/executor chain: signed receipts, opaque resource tokens,
   alias/level/field consent binding, no-follow alias traversal, ledger
   sanitization, bounded service concurrency.
2. The connectors: single validated reference for check and path construction,
   account-identity enforcement in call(), dispatch-body validation before
   transport, response and error-body caps, workflow allowlist coverage.
3. Core dispatch: evidence-class provenance (a provider claim cannot upgrade
   it), boundary classification derived from the actual payload, results
   persisted only after verification, recursive bounded typed payloads.
4. Polling sync: bounded, never-forgetting seen registry.

Please report with the same findings template: number, severity, component,
finding, reproducing test/input, suggested fix. State explicitly which of
F01-F22 you consider closed, which remain open, and any new findings.

Two findings need the canonical text again: **F06** and **F20** were recorded in
your report but the working notes carry no individually captured description,
so this repository does not claim them closed (see
docs/REVIEW_FINDINGS.md). Please re-issue their exact text and the reproducing
input, and this head will be tested and remediated against it.

Known remaining HOLDs (not to be "fixed" by code): host-level process
authentication, OS confinement, live provider/GitHub behaviour,
clean-machine acceptance, and the CI run for this head (the owner-authorized
push had not happened when this request was prepared).
