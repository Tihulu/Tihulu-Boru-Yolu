"""F20: prove that a review pin names the exact code under examination."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        raise ValueError("git history verification failed: " + args[0])
    return result.stdout


def verify_revision(root, pin, head="HEAD"):
    """Accept an exact revision or a linear, entirely docs-only successor.

    Reject merges in the exception interval instead of guessing which parent
    represents the reviewed tree. CI checks out the exact PR head, not GitHub's
    synthetic merge commit. Inspect each individual commit, including reverts.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise ValueError("review pin must be a full commit SHA")
    pinned = _git(root, "rev-parse", "--verify", pin + "^{commit}").decode().strip()
    current = _git(root, "rev-parse", "--verify", head + "^{commit}").decode().strip()
    if pinned == current:
        return
    _git(root, "merge-base", "--is-ancestor", pinned, current)
    history = _git(root, "rev-list", "--reverse", "--parents",
                   pinned + ".." + current).decode().splitlines()
    previous = pinned
    for line in history:
        parts = line.split()
        if len(parts) != 2 or parts[1] != previous:
            raise ValueError("non-linear review history")
        commit, parent = parts
        changed = _git(root, "diff-tree", "--no-commit-id", "--name-only",
                       "-r", "-z", "--no-renames", parent, commit).split(b"\0")
        if any(path and not path.startswith((b"docs/", b"harness/")) for path in changed):
            raise ValueError("production change after review pin: " + commit)
        previous = commit
    if previous != current:
        raise ValueError("review history incomplete")


def verify_package(root="."):
    package = (Path(root) / "docs/REVIEW_PACKAGE.md").read_text(encoding="utf-8")
    match = re.search(r"head under review: `([0-9a-f]{40})`", package)
    if match is None:
        raise ValueError("review package has no full revision pin")
    verify_revision(root, match.group(1))
