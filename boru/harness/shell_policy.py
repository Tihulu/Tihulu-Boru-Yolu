"""Fail-closed command deny floor for the sandbox decision layer (ADR 0006).

`SandboxBroker.authorize()` decides whether a cloud-directed
``run_synthetic_command`` is permitted, but the sandbox itself is a *decision*
layer in this slice: no subprocess is ever run. This module hardens that
**decision** so a dangerous command string is refused before it can be
authorized, ahead of any future execution path.

Design references: LEO's ``deny_commands`` + hardline patterns and OpenHawk's
per-agent permission manifest. It is a pure function: it never executes, opens a
socket, or reads the environment.

Guarantees:
* **fail-closed** — a non-string, empty, whitespace-only, control-carrying or
  oversized command is refused (``command_unsafe``), never allowed by default;
* **deny-before-allow** — an explicit deny pattern wins over any allow rule;
* **bounded** — command length and pattern count are bounded so a hostile input
  cannot exhaust memory;
* **no shell metacharacter laundering** — ``&&``/``;``/``|`` chained commands
  are split and each segment is checked, so ``ls && rm -rf /`` is refused.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence, Tuple

from ..errors import PolicyViolation

#: A command is a small typed document, never an unbounded blob.
MAX_COMMAND_CHARS = 1024
MAX_DENY_PATTERNS = 64
MAX_SEGMENTS = 16

#: Hardline patterns that are **always** denied, before any allow rule and
#: regardless of the configured policy. These model catastrophic, recursive or
#: remote-code patterns that no legitimate synthetic command needs.
HARDLINE_DENY: Tuple[Tuple[str, str], ...] = (
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", "recursive_force_delete"),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;", "fork_bomb"),
    (r"\bmkfs\b|\bdd\b\s+if=|\bwipefs\b|\bshred\b", "disk_destroy"),
    (r"\b(curl|wget)\b[^\n]*\|\s*(sudo\s+)?(ba|z|fi)?sh\b", "remote_code_pipe"),
    (r">\s*/dev/(sd[a-z]|nvme\d+n\d+|hd[a-z]|mmcblk\d)", "raw_device_write"),
    (r"\bchmod\s+(-R\s+)?0{0,3}777\s+/", "world_writable_root"),
    (r"\bgit\s+push\b[^\n]*(--force\b|-f\b)", "force_push"),
    (r"\bgit\s+reset\s+--hard\b", "hard_reset"),
    (r":(){ :|:& };:", "fork_bomb_alt"),
)

#: Characters that terminate or chain a shell command. A command carrying any of
#: these is split into segments and every segment is checked independently, so a
#: safe prefix cannot launder a dangerous suffix.
_CHAIN_SPLIT = re.compile(r"(?:&&|\|\||;|\||\n)")
#: Shell tokens that can redirect or substitute in ways the splitter cannot see.
_METACHARS = re.compile(r"[`$]|\\\n")

_PATTERN_CACHE: dict = {}


def _compiled(pattern: str) -> "re.Pattern":
    cached = _PATTERN_CACHE.get(pattern)
    if cached is None:
        cached = re.compile(pattern, re.IGNORECASE)
        _PATTERN_CACHE[pattern] = cached
    return cached


def _bounded_command(command: str) -> str:
    """Validate the raw command string; refuse anything unsafe to even inspect."""
    if not isinstance(command, str):
        raise PolicyViolation("command must be a string")
    if not command or command.strip() != command:
        raise PolicyViolation("command must be a bounded non-empty string")
    if len(command) > MAX_COMMAND_CHARS:
        raise PolicyViolation("command exceeds the bounded length")
    for character in command:
        if ord(character) < 0x20 or ord(character) == 0x7F:
            raise PolicyViolation("command carries a control character")
    return command


def _segments(command: str) -> Tuple[str, ...]:
    """Split a chained command into analyzable segments (bounded)."""
    parts = [segment.strip() for segment in _CHAIN_SPLIT.split(command)]
    parts = [segment for segment in parts if segment]
    if len(parts) > MAX_SEGMENTS:
        raise PolicyViolation("command has too many chained segments")
    return tuple(parts)


def deny_floor(command: str) -> Tuple[bool, Optional[str]]:
    """Return ``(allowed, reason)`` for one command under the hardline floor.

    ``allowed`` is ``True`` only when the command is safe to even consider;
    every hardline match — in any chained segment — returns ``(False, reason)``.
    Raises :class:`PolicyViolation` for a malformed command, so a caller that
    catches nothing fails closed.
    """
    if not isinstance(command, str):
        raise PolicyViolation("command must be a string")
    checked = _bounded_command(command)
    # 1. Whole-command scan FIRST. Hardline patterns may themselves contain the
    #    chain metacharacters (a fork bomb carries ``|``, a remote-code pipe
    #    carries ``|``, ``&&``/``;`` chains glue a safe head to a dangerous
    #    tail), so they must be matched before any segment splitting destroys
    #    them. This is the ordering defect the regression tests pin.
    for pattern, reason in HARDLINE_DENY:
        if _compiled(pattern).search(checked):
            return False, reason
    # 2. Per-segment scan as an additive catch, so a dangerous token hidden in
    #    one chained segment is still refused even without a cross-segment glue.
    for segment in _segments(checked):
        for pattern, reason in HARDLINE_DENY:
            if _compiled(pattern).search(segment):
                return False, reason
        if _METACHARS.search(segment) and _substitution_is_dangerous(segment):
            return False, "command_substitution"
    return True, None


def _substitution_is_dangerous(segment: str) -> bool:
    """A ``$()``/backtick substitution is only dangerous if it hides a hardline token."""
    inner = _METACHARS.sub(" ", segment)
    for pattern, _reason in HARDLINE_DENY:
        if _compiled(pattern).search(inner):
            return True
    return False


def command_allowed(command: str, *, deny_patterns: Sequence[str] = ()) -> Tuple[bool, Optional[str]]:
    """Decide one command: hardline floor first, then owner deny patterns.

    The hardline floor is unconditional. Owner-supplied ``deny_patterns`` are
    additional (bounded) regular expressions; a match refuses the command.
    Returns ``(allowed, reason)`` and never executes anything.
    """
    allowed, reason = deny_floor(command)
    if not allowed:
        return False, reason
    if not isinstance(deny_patterns, (list, tuple)):
        raise PolicyViolation("deny_patterns must be a bounded sequence")
    if len(deny_patterns) > MAX_DENY_PATTERNS:
        raise PolicyViolation("too many deny patterns")
    for raw in deny_patterns:
        if not isinstance(raw, str) or not raw or len(raw) > 256:
            raise PolicyViolation("deny pattern must be a bounded non-empty string")
        try:
            compiled = _compiled(raw)
        except re.error:
            # A malformed owner pattern fails closed rather than being ignored.
            raise PolicyViolation("deny pattern is not a valid expression")
        if compiled.search(command):
            return False, "denied_by_pattern"
    return True, None


def allowed_segments(command: str) -> Tuple[str, ...]:
    """Return the analyzable segments of a command (for callers that audit)."""
    return _segments(_bounded_command(command))
