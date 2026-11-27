"""Read-only local observability console for Boru Core (ADR 0005).

Design references: OpenHawk's HawkEye TUI and LEO's ``leo tui``. This is the
opposite of an authorization surface: it **renders** the state Boru Core already
holds and can **change nothing**. It starts no provider call, widens no policy
axis, and releases no private data. Internal content (tokens, secrets, raw host
output) is redacted before it reaches this layer.

The console is split so the interesting logic is pure and testable:

* :func:`snapshot` - assemble a bounded, secret-free view of the running system;
* :func:`render` - format that view as text (used by tests and ``--once``);
* :func:`run` - the optional interactive loop (stdlib ``curses``), the only
  interactive piece, disabled by default and safe to skip on a headless host.

There is no third-party dependency and no network listener.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: A rendered view is a small, bounded document.
MAX_TITLE = 64
MAX_NOTE = 160

_AXIS_KEYS: Tuple[Tuple[str, str], ...] = (
    ("optimization_mode", "optimization"),
    ("inference_scope", "inference"),
    ("execution_profile", "execution"),
    ("disclosure_policy", "disclosure"),
)


@dataclass(frozen=True)
class HarnessSnapshot:
    """A bounded, secret-free view of Boru Core for the console."""

    at: float
    axes: Tuple[Tuple[str, str], ...]
    workers: Tuple[Tuple[str, str], ...]
    budget: Tuple[Tuple[str, int], ...]
    queue: Tuple[Tuple[str, int], ...]
    ledger_tail: Tuple[Tuple[str, str], ...]
    notes: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "at": self.at,
            "axes": [list(row) for row in self.axes],
            "workers": [list(row) for row in self.workers],
            "budget": [list(row) for row in self.budget],
            "queue": [list(row) for row in self.queue],
            "ledger_tail": [list(row) for row in self.ledger_tail],
            "notes": list(self.notes),
        }


def _axes(policy_state: Any) -> Tuple[Tuple[str, str], ...]:
    """Extract the four independent axes from a policy/state object."""
    axes: List[Tuple[str, str]] = []
    for key, label in _AXIS_KEYS:
        value = _read(policy_state, key)
        axes.append((label, "unset" if value is None else str(_truncate(value, MAX_NOTE))))
    return tuple(axes)


def _workers(registry: Any) -> Tuple[Tuple[str, str], ...]:
    """Extract worker/agent identity and state without any secret."""
    workers: List[Tuple[str, str]] = []
    for record in _iter(registry, "workers"):
        worker_id = _read(record, "worker_id") or _read(record, "id") or "?"
        state = _read(record, "state") or _read(record, "status") or "unknown"
        workers.append((str(_truncate(worker_id, MAX_TITLE)), str(_truncate(state, MAX_TITLE))))
    return tuple(workers)


def _budget(component: Any) -> Tuple[Tuple[str, int], ...]:
    """Extract bounded authorization and call budgets."""
    rows: List[Tuple[str, int]] = []
    used = _read(component, "authorization_count")
    if used is None:
        used = _read(component, "count")
    maximum = _read(component, "max_authorization_requests")
    if maximum is None:
        maximum = _read(component, "max_requests")
    if isinstance(used, int) and isinstance(maximum, int):
        rows.append(("authorization", int(used) if int(used) <= maximum else maximum))
        rows.append(("authorization_max", int(maximum)))
    return tuple(rows)


def _queue(scheduler: Any) -> Tuple[Tuple[str, int], ...]:
    """Extract bounded queue depth information from a scheduler."""
    rows: List[Tuple[str, int]] = []
    pending = _read(scheduler, "pending")
    if pending is None:
        pending = _read(scheduler, "queue_depth")
    running = _read(scheduler, "running")
    if isinstance(pending, int):
        rows.append(("pending", int(pending)))
    if isinstance(running, int):
        rows.append(("running", int(running)))
    return tuple(rows)


def _ledger_tail(ledger: Any, limit: int = 8) -> Tuple[Tuple[str, str], ...]:
    """Return a bounded, redacted tail of the rejection ledger."""
    entries = _iter(ledger, "entries")
    if not entries:
        entries = _iter(ledger, "records")
    tail: List[Tuple[str, str]] = []
    for entry in list(entries)[-limit:]:
        reason = _read(entry, "reason") or "?"
        tail.append((str(_truncate(reason, MAX_TITLE)), str(_truncate(int(time.time()), 20))))
    return tuple(tail)


def snapshot(policy_state: Any = None, registry: Any = None, component: Any = None,
             scheduler: Any = None, ledger: Any = None, now: Optional[float] = None) -> HarnessSnapshot:
    """Assemble a bounded, secret-free view of Boru Core.

    Every argument is optional and may be ``None`` (an empty view is valid);
    the function never raises for a missing field and never reads a secret. The
    result contains only bounded, redacted strings and small integers.
    """
    return HarnessSnapshot(
        at=time.time() if now is None else float(now),
        axes=_axes(policy_state),
        workers=_workers(registry),
        budget=_budget(component),
        queue=_queue(scheduler),
        ledger_tail=_ledger_tail(ledger),
        notes=("read-only; no authorization surface", "leaks no tokens or host output"),
    )


def render(view: HarnessSnapshot) -> str:
    """Format a :class:`HarnessSnapshot` as plain text (loopback only)."""
    lines: List[str] = []
    lines.append("Boru Harness - read-only observability")
    lines.append("axes:")
    for label, value in view.axes:
        lines.append("  {:<14} {}".format(label, value))
    if view.workers:
        lines.append("workers:")
        for worker_id, state in view.workers:
            lines.append("  {:<24} {}".format(worker_id, state))
    if view.budget:
        lines.append("budget:")
        for name, value in view.budget:
            lines.append("  {:<20} {}".format(name, value))
    if view.queue:
        lines.append("queue:")
        for name, value in view.queue:
            lines.append("  {:<20} {}".format(name, value))
    if view.ledger_tail:
        lines.append("recent denials:")
        for reason, stamp in view.ledger_tail:
            lines.append("  {:<24} {}".format(reason, stamp))
    lines.append("notes: " + "; ".join(view.notes))
    return "\n".join(lines)


def run(view_factory, *, once: bool = False, interval: float = 2.0) -> int:
    """Optional interactive loop. Disabled by default; ``once`` renders one frame.

    ``view_factory`` is a zero-arg callable returning a :class:`HarnessSnapshot`.
    The interactive path uses stdlib ``curses`` and is skipped gracefully on a
    headless host. It performs no I/O beyond the terminal and releases nothing.
    """
    if once:
        print(render(view_factory()))
        return 0
    try:
        import curses
    except Exception:
        print(render(view_factory()))
        return 0

    def _loop(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        while True:
            stdscr.erase()
            text = render(view_factory())
            cols = getattr(curses, "COLS", 0) or 0
            stdscr.addstr(0, 0, text[: cols - 1] if cols > 1 else "")
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break
            curses.napms(int(interval * 1000))

    try:
        curses.wrapper(_loop)
    except Exception:
        print(render(view_factory()))
    return 0


# --- bounded, defensive accessors (never a source of a secret) --------------

def _read(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _iter(obj: Any, key: str) -> Sequence[Any]:
    value = _read(obj, key)
    if callable(value):
        try:
            value = value()
        except Exception:
            return ()
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _truncate(value: Any, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "..."
