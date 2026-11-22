# Gate 3 connector pilot — runbook

The pilot runs against a **private, disposable** repository the owner creates
(`docs/OWNER_GATE_GUIDE.md`, Gate 3). Nothing is merged, published or deleted;
the write pilot creates a branch, a file commit and a DRAFT pull request, and
the Actions pilot only dispatches a workflow the repository already owns.

## What the owner provides

| Value | Where it goes |
| --- | --- |
| Account + repository (`owner/<disposable>`) | `--account`, `--repository` |
| Token | the **environment variable NAME** (`--token-env`); the value is never an argument, a file or a log line |
| Reference and workflow file | `--reference`, `--workflow` (the repository must contain a `workflow_dispatch` workflow with no secrets) |

## Step 1 — pre-flight, before the token is spent

~~~bash
BORU_PILOT_TOKEN_GH=<token> python3 scripts/connector_pilot.py \
  --account <owner> --repository <owner>/<disposable> \
  --token-env BORU_PILOT_TOKEN_GH --workflow ci.yml --dry-run
~~~

A dry-run makes **no outbound request** (the transport refuses any exchange, so
the claim is enforced by construction). It proves the four grant-bound denials:
another repository, another reference, an ungranted operation and an ungranted
workflow. A missing credential refuses with `not_ready` before anything else.

## Step 2 — the live pilot

Drop `--dry-run`. The script runs, in order:

1. **denials** — the four out-of-scope pairs above, each with its reason;
2. **read pilot** — `list_issues`, `list_branches`, `get_commit`, `read_file`,
   `list_workflows` (object IDs recorded);
3. **write pilot** — `create_branch`, `put_file`, `create_pull` (draft only);
4. **Actions pilot** — `dispatch_workflow` and `list_workflows`; run/job
   inspection, rerun and cancel run against the run id the dispatch returns.

## Evidence for PASS

Record in `harness/build-log.md`: the real object IDs (issue/branch/commit/PR
numbers, run and job ids), the four denial reasons verbatim, the account
identity check outcome, and the fact that nothing was merged or published. A
failure is recorded as a failure; a skipped step is recorded as skipped.

## Safety rails

* the repository is owner-declared — the script never guesses one;
* a missing credential refuses before any request;
* the account identity is verified per provider before a repository call, and a
  mismatch refuses it (`identity_is_not_inference` stays true);
* the token never appears in output, the ledger or a log.
