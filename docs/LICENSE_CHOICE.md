# License choice — decision matrix for the owner

This repository has **no `LICENSE` file**, which means "all rights reserved":
nobody may use, copy or distribute it. Gate 5 requires the owner to choose one
and add it. This document compares the candidates against what this project
actually is; **the choice is the owner's**, and no license is added here.

## What the project is

* A local-first orchestration core (Boru Core) plus optional connectors to
  third-party services (Jan, OpenCode, GitHub, GitLab, AI providers).
* Distributed as source and as a user-space install script; no service, no
  telemetry, no backend.
* Documentation and tests are part of the deliverable.
* The security posture depends on code being auditable by whoever runs it.

## Candidates

| License | Allows | Requires | Patent grant | Notes for this project |
| --- | --- | --- | --- | --- |
| `MIT` | Anything, including proprietary forks | The notice is kept | No | Simplest; maximizes adoption; no explicit patent clause |
| `Apache-2.0` | Anything, including proprietary forks | The notice, and a `NOTICE` if one is added, plus stating changes | **Yes** | Common for AI/ML-adjacent tooling; a patent clause matters when a patent-holders' ecosystem is involved |
| `AGPL-3.0` | Anything | Derivative source under the same license, **including over a network** | Yes | Strong copyleft; if a hosted Boru service ever appears, its source must be published — a deliberate choice, not a default |
| `BSD-3-Clause` | Anything except using the name for endorsement | The notice and the no-endorsement clause | No | Similar to MIT with a name-protection clause |

## What the choice does *not* affect

* The security defaults (`LOCAL_ONLY`, `LOCAL_ISOLATED`, `MINIMUM_NECESSARY`),
  the privacy boundaries and the connector scope checks are implementation
  properties, not license properties.
* A permissive license does not weaken the gates; a copyleft license does not
  strengthen them.

## Recommendation (for the owner to accept or reject)

`Apache-2.0` if a patent clause is wanted alongside wide reuse; otherwise `MIT`
for the smallest legal surface. Both keep the "run it, read it, audit it"
property this repository's security model relies on. If the owner wants every
hosted derivative to publish its source, choose `AGPL-3.0` knowingly.

## Once chosen

1. The owner states the license; the agent adds the `LICENSE` file with the
   correct copyright line and year.
2. `scripts/install_boru.sh` already copies `LICENSE` into the install tree when
   present, so the file lands in the installed distribution.
3. The manifest in `scripts/check_project.py` is extended to require the file,
   so a release cannot be built without it.
4. Record the decision and the reason in `harness/build-log.md`; Gate 5's PASS
   also needs the PR reviewed and merged by the owner.
