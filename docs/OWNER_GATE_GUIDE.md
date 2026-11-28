# Owner gate guide — five gates, in order

This is the order in which the remaining work happens. Each gate has a
definition of PASS, the owner's action, and what the development agent does.
Nothing here authorizes host installs, credentials, paid API use, merges or
releases by itself.

## Gate 1 — Independent security review (P5 broker chain)

**PASS:** no unresolved critical or high finding; medium findings fixed or
explicitly accepted; reviewer, date and commit recorded in the ledger.

**Owner action:** nominate a reviewer with repository read access and give them
`docs/SECURITY_REVIEW_REQUEST.md`.

**Agent action:** fix findings, add regression tests, re-run the suite, record.

**Cannot start without:** a named human reviewer.

## Gate 2 — Provider registration + live OAuth round trip (P7)

**PASS:** a real authorization callback captured on loopback, verified `state`,
a stored opaque handle, a real authorized model response with the provider's
model ID, and a recorded distinction between identity and inference.

**Owner action:**
1. Pick the first provider. Recommended order: **Google/Gemini** (documented
   authorization-code + PKCE, no consumer-plan inference ambiguity) or
   **OpenAI** if the "Sign in with ChatGPT" eligibility applies.
2. Register an OAuth client in the provider console: application type
   *desktop/native or web*, authorization redirect URI
   `http://127.0.0.1:8731/callback`, PKCE `S256`, no implicit flow.
3. Send the **client_id** only. Never send a client secret; if a secret is
   required it goes into an environment variable on your machine.

**Agent action:** run `python3 -m boru connect …` with `--no-browser` or a
system browser, capture the callback, store an opaque handle, and report
`connection_state`, `scope` and `model_test_passed` honestly.

## Gate 3 — Disposable repository + live connector pilot (P8)

**PASS:** real provider-backed object IDs for a read, a branch, a file commit, a
draft PR, a workflow dispatch, its run/job inspection, a rerun and a cancel;
plus proven denials for out-of-scope repository, reference, workflow and
operation.

**Owner action:** create a **private, disposable** repository (or explicitly
authorize the agent to create one) and approve the credential/scope to use.
For GitHub Actions the repository must have a workflow with `workflow_dispatch`
and no secrets.

**Agent action:** run the read-only pilot first, then the write pilot, then the
Actions pilot, recording object IDs and denials; nothing is merged or published.
The runbook is `docs/CONNECTOR_PILOT_RUNBOOK.md` and the script is
`scripts/connector_pilot.py` — its `--dry-run` proves the grant-bound denials
with no outbound request before the owner's token is spent.

## Gate 4 — Clean-machine acceptance (P10, M01–M12)

**PASS:** every mandatory matrix row PASS on Pop!_OS 24.04 x86_64 **and** Ubuntu
24.04 LTS x86_64, including offline and partial-outage runs, and a verified
rollback.

**Owner action:** provide two clean machines or VMs. On each image, first run
`python3 -m boru doctor --state-dir local-state` (must print `overall: ok`),
then follow `docs/OS_ACCEPTANCE.md` M01–M12 in order and send back the results.

**Agent action:** prepare commands, record dated evidence in the ledger, and fix
anything that fails.

## Gate 5 — License and release approval (P10)

**PASS:** a repository license chosen and added; the PR reviewed and merged by
the owner; release notes and a version tag prepared; the owner explicitly
approves distribution.

**Owner action:** choose a license and approve the merge/release.

**Agent action:** add the chosen `LICENSE`, finalize documentation, prepare the
release notes, and stop for your GO/NO-GO.

## Status of each gate

| Gate | State |
| --- | --- |
| 1 — Security review | **HOLD** (reviewer needed) |
| 2 — Provider OAuth | **HOLD** (registration needed) |
| 3 — Connector pilot | **HOLD** (disposable repository needed) |
| 4 — Clean-machine matrix | **HOLD** (images needed) |
| 5 — License/release | **HOLD** (owner decision) |
