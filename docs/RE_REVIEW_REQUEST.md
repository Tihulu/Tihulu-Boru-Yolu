# Re-review request — TIHULU Boru Yolu, Gate 1 (second re-review)

Repository: https://github.com/Tihulu/Tihulu-Boru-Yolu
Branch: `p1/boru-core-vertical-slice` (draft PR #14)
Code head under review: `HEAD` (branch head at the time you read this)
CI: the Actions run for this head is green (see the PR's checks).

**What changed since your re-review of `1617709`:**

Your report returned FAIL/DO NOT APPROVE with findings F03, F06, F07, F12, F14,
F15, F17, F20 and five new findings N01–N05. Each was first reproduced against
the tree, then remediated, then closed with a named negative regression test in
`tests/test_rereview_regressions.py` (20 tests, two or more per finding):

| # | Remediation |
| --- | --- |
| F03 | The alias is required and matched in both consent stores; a legacy alias-less row denies rather than matching |
| F06 | The permitted scopes come from the authenticated registry record; a request that declares more or less than it holds is refused |
| F07 | The cached connector identity is a fingerprint of (provider, token); every externally connected path verifies identity and counts its usage |
| F12 | Schema version 3: grant_id globally unique; a version-2 store migrates and refuses an ambiguous history; a revoked id is a tombstone |
| F14 | Capacity is acquired before a thread spawns; an excess connection is refused on a drained request through the instance method |
| F15 | The GitHub exchange caps its HTTP error body, as the account request already did |
| F17 | A used nonce outlives its grant; an expired grant's nonce is dropped; past the bound the store rolls the insert back and refuses rather than evicting a live nonce |
| N01 | Grant timestamps must be finite, positive and ordered |
| N02 | Workflow discovery verifies identity and charges the grant |
| N03 | The worker returns exactly the fields the receipt names |
| N04 | A dispatch with inputs and no owner-supplied declaration is refused |
| N05 | A restored polling registry is bounded as it is loaded |
| F20 | The review package names the head it describes (HEAD or an ancestor) |

**Please run, from a clone of the branch:**
```
python3 scripts/check_project.py
python3 -m unittest discover -s tests      # 701 tests ... OK
PYTHONPATH=. python3 tests/test_review_regressions.py
PYTHONPATH=. python3 tests/test_rereview_regressions.py
python3 scripts/evidence.py                # exit 0
python3 -m boru doctor --state-dir local-state
python3 -m boru demo
```

**Please state:** which of F03/F06/F07/F12/F14/F15/F17/N01–N05 you now consider
closed, which remain open, and any new findings — with the same findings
template (number, severity, component, finding, reproducing test/input,
suggested fix).

**Still outstanding from the earlier review:** the canonical text and
reproducing input for **F06** and **F20** as originally issued. This repository
does not claim those two closed on its own authority, and this request asks for
the exact text again.

**Known remaining HOLDs (not to be "fixed" by code):** host-level process
authentication, OS confinement, live provider/GitHub behaviour and
clean-machine acceptance.
