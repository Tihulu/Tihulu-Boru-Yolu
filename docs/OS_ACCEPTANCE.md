# Clean-machine acceptance matrix and rollback checklist (P10)

This document makes the remaining owner-run acceptance work executable. Nothing
here is claimed to have passed: every row starts as **HOLD** until an owner runs
it on a real machine and records the result in `harness/build-log.md` with the
date, OS release, Boru commit, tester and sanitized outcome.

## Scope

- Pop!_OS 24.04 x86_64 (COSMIC/Wayland) and Ubuntu 24.04 LTS x86_64 first;
  Ubuntu LTS versions are added only after they are actually verified.
- Disposable machines or VMs only. **Never** run the first install on a machine
  that holds live Jan/OpenCode state.

## Pre-flight (owner)

1. Confirm Jan and OpenCode versions, loaded models and active sessions
   locally; record them in the local-only ledger (never in this repository).
2. Confirm no port conflict on the ports this repository may bind
   (`python3 -m boru` binds none by default; the dashboard binds loopback only).
3. Back up only affected owned files, then test a restore in a disposable copy.
4. Verify a fresh, offline-capable model is downloaded in Jan.

## Matrix

| ID | Test | Expected | Record |
| --- | --- | --- | --- |
| M01 | Install Boru Core user-space on a clean Pop!_OS 24.04 x86_64 image (`scripts/install_boru.sh`) | Exit 0; only the named target/state/bin directories are created; owner-only modes (0700/0600) | date, image, tester |
| M02 | Same on Ubuntu 24.04 LTS x86_64 | Same | date, image, tester |
| M03 | `python3 -m boru demo` on each image | `REVIEW`, `evidence_class=simulated`, `live_acceptance=HOLD` | sanitized output |
| M04 | Uninstall (`scripts/uninstall_boru.sh`) | Only Boru-owned paths removed; nothing else touched | verification listing |
| M05 | `python3 scripts/evidence.py` on each image | Exit 0 with all mandatory checks PASS | full report block |
| M06 | Offline run (no internet) with a local Jan model | Same behaviour as M03; no cloud endpoints contacted | date, tester |
| M07 | A21 direct Jan 3-turn chat on a clean image | `REVIEW`/`direct` with the allowlisted model ID and measured usage | provider/model/request IDs |
| M08 | Optional OpenCode child session in a disposable directory | Real session/message IDs, agent, model and provider identity recorded; session deleted | IDs |
| M09 | Ports and processes | No non-loopback listener; no Boru-owned background service after stop; no autostart entry | `ss -ltn` summary |
| M10 | Partial outage: cloud provider unavailable | Only permitted fallback; LOCAL_ONLY yields zero remote calls; budget holds, never escalated | test log summary |
| M11 | Revocation and cancellation | Revoked consent denies; cancelled tasks release leases; interrupted tasks return to HOLD on restart | ledger rows |
| M12 | Rollback after a failed install | Restore from backup reproduces the pre-install state; Jan/OpenCode unchanged | verification listing |

## Rollback checklist (owner)

1. Stop Boru-owned services only: `boru` processes and the loopback dashboard.
2. Run `scripts/uninstall_boru.sh --target <dir> --state-dir <dir> --bin-dir <dir>`
   (add `--dry-run` first to see exactly what would be removed).
3. Remove the worker/consent/audit directories only if they were Boru-created.
4. Restore the backup taken in pre-flight step 3 and verify Jan and OpenCode
   start with unchanged configuration, models, providers and sessions.
5. Record the result in `harness/build-log.md`; keep evidence out of this
   public repository.

## Out of scope for v1

- Unrestricted root/host Shell for cloud agents.
- Docker socket access, privileged containers, host PID/network sharing.
- Public listeners, reverse proxies, remote or self-hosted CI runners.
- Automatic release, deployment or background autostart.

## Status

**HOLD — no clean-machine run has been performed by this repository.** The only
live evidence so far is A21 and A23 on the owner's development host, recorded in
`harness/build-log.md`.
