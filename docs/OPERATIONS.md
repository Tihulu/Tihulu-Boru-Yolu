# Operations, rollback and status discipline

## Run-state principles

- Existing Jan and OpenCode remain the owner-managed production services; Boru never silently stops/restarts or reconfigures them.
- Keep new Kandev, Langflow, router, broker and sandbox services disabled on boot for the pilot.
- Treat active agent sessions as shared resources; pause or defer model unload while an unrelated client holds a lease.
- Avoid automatic release upgrades; use pinned versions and verify checksums.
- Do not copy full chats, command transcripts or private hardware inventories to GitHub/CI.

## Install ledger (local-only)

Record local-only component versions, package hashes, active data directories, bind addresses, snapshots and owner approvals. Keep local ledger out of this public repo. Public report gets sanitized PASS/FAIL/HOLD, commit IDs and test classes, not raw host details.

## Startup dependencies

Kandev/board can start without Langflow or broker. Langflow can start without Jan; mark model component unavailable. Jan/OpenCode operate independently of Boru. Router can answer health/status without broker but cannot execute restricted operations. Cloud Shell must not be enabled unless authenticated broker + sandbox + consent store are healthy.

## Stop / cleanup

Stop only Boru-owned test jobs and newly installed services on owner request. For model resources: release session lease, verify no other clients, request unload through documented Jan API only if owned and supported. Never `kill -9` arbitrary processes, clear global swap, reset GPU drivers or remove foreign data to "fix" an OOM.

## Backups and migration

Before each approved change:
1. Capture file list, version and checksum of only the affected owned files.
2. Take local owner-only backup without exporting secrets.
3. Apply to disposable/test environment first.
4. Run syntax/config/multi-turn regression checks.
5. Restore original state if any invariant fails.
6. Keep immutable history of decision, test evidence and migration revision in Git.

No one-click production upgrade exists yet.

## Observability

Publish only:
- task and attempt IDs (random public-safe aliases), state, model family alias, measured/estimated token totals, result type and test counts;
- broker decision reason enums, audit receipt IDs and latencies;
- safe memory/VRAM aggregates with no unrelated process inventory.

Do not enable unrestricted verbose tracing or provider telemetry in privacy-preserving profiles.

## Incident response

If permission bypass, unexpected port binding, raw output disclosure, unapproved cloud Shell call or foreign-process termination is suspected: deny new tasks, revoke broker-owned grants, stop only affected Boru services and preserve a **private** evidence bundle. Record a sanitized public issue if needed. Do not keep retrying a provider safety-policy denial.

## Done definition

A milestone is DONE only when the relevant tests were executed and recorded; architecture docs and syntactic checks are not production acceptance. The repo starts at architectural/bootstrap status, not at a fabricated percentage.
