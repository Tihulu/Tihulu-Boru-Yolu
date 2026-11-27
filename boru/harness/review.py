"""Interactive owner-review console for tasks awaiting a decision (ADR 0005).

Design reference: LEO's approval gates. Boru already authorizes a review through
`BoruCore.review(task_id, accept=...)`, and `boru queue` / `boru review` already
drive it one task per invocation. This console closes the convenience gap for an
operator reviewing a batch: it lists the tasks in `REVIEW` and lets the owner
accept or reject each in one session.

It is **not** an authorization surface. Every decision is routed through the same
`core.review()` path the standalone command uses, so no policy axis is widened
and nothing is decided that Core would refuse.

Safety properties:
* **fail-closed** — a non-interactive stdin, EOF, an unrecognised key or a read
  error decides **nothing** and exits cleanly; silence never means "accept";
* **bounded** — at most `MAX_PROMPTED` tasks are offered, and each decision is
  one bounded call;
* **no free text** — the owner picks from a fixed menu, so no input is ever
  parsed as a command, a path or a credential.
"""
from __future__ import annotations

import sys
from typing import Any, List, Optional, Tuple

#: A review session offers a bounded number of tasks.
MAX_PROMPTED = 32

_PROMPT = "  [a]ccept  [r]eject  [s]kip  [q]uit > "


def _read(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def reviewable_rows(core: Any, limit: int = MAX_PROMPTED) -> List[Any]:
    """Bounded, read-only listing of tasks awaiting the owner's decision."""
    rows: List[Any] = []
    store = getattr(core, "store", None)
    by_state = getattr(store, "by_state", None)
    if callable(by_state):
        try:
            rows = list(by_state(("REVIEW",)))[:limit]
        except Exception:
            rows = []
    return rows


def _decide(core: Any, task_id: str, accept: bool) -> Tuple[bool, Optional[str]]:
    """Route one decision through the existing authorization path."""
    reviewer = getattr(core, "review", None)
    if not callable(reviewer):
        return False, "review_unavailable"
    try:
        reviewer(task_id, accept=accept)
    except Exception as exc:
        return False, str(exc)
    return True, None


def run_interactive(core: Any, *, input_fn=None, output_fn=None) -> Tuple[int, int]:
    """Offer each awaiting task to the owner; return ``(accepted, rejected)``.

    ``input_fn``/``output_fn`` are injectable for tests. A missing TTY, EOF or a
    read error ends the session having decided nothing further.
    """
    read_line = input_fn if input_fn is not None else sys.stdin.readline
    write = output_fn if output_fn is not None else (lambda text: sys.stdout.write(text + "\n"))
    rows = reviewable_rows(core)
    if not rows:
        write("no task awaits review")
        return 0, 0
    accepted = 0
    rejected = 0
    for row in rows:
        task_id = _read(row, "task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            continue
        write("task {} awaits review".format(task_id))
        try:
            answer = read_line(_PROMPT)
        except Exception:
            break
        if not isinstance(answer, str):
            break
        choice = answer.strip().lower()
        if choice in ("a", "accept"):
            ok, reason = _decide(core, task_id, True)
            if ok:
                accepted += 1
                write("  accepted {}".format(task_id))
            else:
                write("  refused {}: {}".format(task_id, reason or "denied"))
        elif choice in ("r", "reject"):
            ok, reason = _decide(core, task_id, False)
            if ok:
                rejected += 1
                write("  rejected {}".format(task_id))
            else:
                write("  refused {}: {}".format(task_id, reason or "denied"))
        elif choice in ("s", "skip", ""):
            continue
        else:
            # An unrecognised key decides nothing and ends the session.
            write("unrecognised choice; nothing further was decided")
            break
    write("summary: {} accepted, {} rejected".format(accepted, rejected))
    return accepted, rejected
