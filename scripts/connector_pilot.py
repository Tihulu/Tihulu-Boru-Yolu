#!/usr/bin/env python3
"""Gate 3 connector pilot: read, write, Actions and denial runs against a
disposable repository, with the evidence a PASS needs.

Safety rails, enforced before any request:
* the repository must be owner-declared (this script never guesses one);
* the token is read from an environment variable NAME given on the command
  line, never from a file, an argument or a log;
* a missing credential refuses the pilot before any outbound request;
* nothing is merged, published or deleted: the write pilot creates a branch,
  a file commit and a DRAFT pull request, and the Actions pilot only dispatches
  a workflow the repository already owns.

Usage:
    BORU_PILOT_TOKEN_GH=... python3 scripts/connector_pilot.py \\
        --account <owner> --repository <owner>/<disposable-repo> \\
        --token-env BORU_PILOT_TOKEN_GH [--workflow ci.yml] [--dry-run]

`--dry-run` runs only the pairs that need no network (the grant denials and the
credential pre-flight), so it can be verified before the owner spends a token.
Without it the pilot performs real calls against the named repository.

Output is a sanitized evidence block: object IDs, decisions and denial reasons,
never a token, a path or a private payload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boru.connectors.base import Capability, Grant  # noqa: E402
from boru.connectors.github import GitHubProvider  # noqa: E402
from boru.errors import ConnectorDenied, PolicyViolation  # noqa: E402

READ_OPERATIONS = ("list_issues", "list_branches", "get_commit", "read_file", "list_workflows")
WRITE_OPERATIONS = ("create_issue", "create_branch", "put_file", "create_pull")
ACTIONS_OPERATIONS = ("dispatch_workflow", "get_run", "rerun_workflow", "cancel_run")


def _grant(operation, account, repository, reference, capabilities, workflow_ids=()):
    return Grant(grant_id="pilot", account=account, repository=repository, reference=reference,
                 operations=(operation,), capabilities=capabilities, max_calls=8,
                 issued_at=time.time(), expires_at=time.time() + 900, nonce="pilot",
                 workflow_ids=workflow_ids)


def _emit(title, payload):
    sys.stdout.write(json.dumps({title: payload}, sort_keys=True, indent=2) + "\n")


def _run(step, call):
    """One pilot step: a typed outcome, never a traceback."""
    try:
        value = call()
        return {"decision": "allow", "value": value}
    except ConnectorDenied as exc:
        return {"decision": "deny", "reason": str(exc)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gate 3 connector pilot (disposable repository)")
    parser.add_argument("--account", required=True, help="grant account, e.g. the repository owner")
    parser.add_argument("--repository", required=True, help="owner/name of the DISPOSABLE repository")
    parser.add_argument("--token-env", required=True, help="environment variable NAME holding the token")
    parser.add_argument("--reference", default="main")
    parser.add_argument("--workflow", default="pilot.yml")
    parser.add_argument("--dry-run", action="store_true",
                        help="run only the credential pre-flight and the grant denials")
    args = parser.parse_args(argv)

    if "/" not in args.repository or args.repository.count("/") != 1:
        _emit("refused", {"error": "configuration_error",
                          "detail": "repository must be owner/name"})
        return 2
    if not os.environ.get(args.token_env):
        # Refuse before any outbound request: a missing credential is not a
        # prompt to try anyway.
        _emit("refused", {"error": "not_ready",
                          "detail": "the token environment variable is not set"})
        return 2
    if args.dry_run:
        # A dry-run proves the grant denials, not the network: the transport
        # refuses any exchange, so the claim "no outbound request was made" is
        # enforced by construction rather than by hoping the denials come first.
        def _refuse(method, path, body):
            raise ConnectorDenied("endpoint_unavailable")

        provider = GitHubProvider(token_env=args.token_env, transport=_refuse)
    else:
        provider = GitHubProvider(token_env=args.token_env)
    evidence = {"repository": args.repository, "reference": args.reference,
                "credential": "present", "identity_is_not_inference": True}

    # -- denials that need no network: a grant never reaches outside itself ----
    denials = {}
    denials["other_repository"] = _run("other_repository", lambda: provider.call(
        _grant("list_issues", args.account, args.repository, args.reference,
               (Capability.REPO_READ,)), "list_issues", {"repository": "someone/else"}))
    denials["other_reference"] = _run("other_reference", lambda: provider.call(
        _grant("list_issues", args.account, args.repository, args.reference,
               (Capability.REPO_READ,)), "list_issues", {"repository": args.repository,
                                                         "reference": "another-ref"}))
    denials["ungranted_operation"] = _run("ungranted_operation", lambda: provider.call(
        _grant("list_issues", args.account, args.repository, args.reference,
               (Capability.REPO_READ,)), "create_issue", {"repository": args.repository}))
    denials["ungranted_workflow"] = _run("ungranted_workflow", lambda: provider.call(
        _grant("rerun_workflow", args.account, args.repository, args.reference,
               (Capability.ACTIONS_DISPATCH,), workflow_ids=("approved.yml",)),
        "rerun_workflow", {"repository": args.repository, "run_id": "1"}))
    evidence["denials"] = denials
    if args.dry_run:
        _emit("pilot", dict(evidence, dry_run=True, note="no outbound request was made"))
        return 0

    # -- read pilot -----------------------------------------------------------
    read = {}
    for operation in READ_OPERATIONS:
        grant = _grant(operation, args.account, args.repository, args.reference,
                       (Capability.REPO_READ,), workflow_ids=(args.workflow,))
        payload = {"repository": args.repository, "reference": args.reference,
                   "path": "README.md", "workflow": args.workflow}
        read[operation] = _run(operation, lambda op=operation, g=grant, p=payload: provider.call(g, op, p))
    evidence["read"] = read

    # -- write pilot: a branch, a file commit and a DRAFT pull request --------
    stamp = str(int(time.time()))
    branch = "boru-pilot-" + stamp
    write = {}
    write["create_branch"] = _run("create_branch", lambda: provider.call(
        _grant("create_branch", args.account, args.repository, args.reference,
               (Capability.CODE_PR_WRITE,)), "create_branch",
        {"repository": args.repository, "branch": "boru-pilot-" + stamp}))
    write["put_file"] = _run("put_file", lambda: provider.call(
        _grant("put_file", args.account, args.repository, args.reference,
               (Capability.CODE_PR_WRITE,)), "put_file",
        {"repository": args.repository, "path": "boru-pilot-" + stamp + ".txt",
         "content": "boru connector pilot " + stamp}))
    write["create_pull"] = _run("create_pull", lambda: provider.call(
        _grant("create_pull", args.account, args.repository, args.reference,
               (Capability.CODE_PR_WRITE,)), "create_pull",
        {"repository": args.repository, "branch": "boru-pilot-" + stamp,
         "title": "Boru connector pilot " + stamp}))
    evidence["write"] = write
    evidence["write_note"] = ("draft pull request only; nothing is merged, "
                              "published or deleted")

    # -- Actions pilot: dispatch, inspect, rerun, cancel ----------------------
    actions = {}
    grant = _grant("dispatch_workflow", args.account, args.repository, args.reference,
                   (Capability.ACTIONS_DISPATCH,), workflow_ids=(args.workflow,))
    actions["dispatch_workflow"] = _run("dispatch_workflow", lambda: provider.call(
        grant, "dispatch_workflow", {"repository": args.repository, "workflow": args.workflow},
        body={"ref": args.reference, "inputs": {}}))
    actions["list_workflows"] = _run("list_workflows", lambda: provider.list_workflows_typed(
        grant, {"repository": args.repository, "reference": args.reference,
                "workflow": args.workflow}))
    actions["note"] = ("run/job inspection, rerun and cancel need a run id from the "
                       "dispatch result; run them with that id once the dispatch has one")
    evidence["actions"] = actions
    _emit("pilot", dict(evidence, dry_run=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PolicyViolation as exc:
        _emit("refused", {"error": "policy_violation", "detail": str(exc)})
        raise SystemExit(2)
