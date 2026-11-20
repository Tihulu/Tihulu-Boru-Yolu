"""Token/cost budgets, cooldowns and context compaction (P3 slice).

Two rules are enforced honestly:

* estimates are **labelled estimates**. Boru never claims an exact count it
  cannot observe, and never reports an observation that did not happen;
* a hard ceiling is checked *before* dispatch when possible and rechecked
  against actually reported usage afterwards. Exceeding a ceiling holds the
  task; it never triggers a wider permission or a silent extra call.

The compactor is a deterministic heuristic, not a semantic summarizer: it keeps
the system instruction and the most recent turns inside a bounded character
budget and reports what it dropped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .errors import PolicyViolation
from .providers.base import ChatMessage

#: Deterministic character heuristic used only for bounded estimates.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Bounded estimate; labelled ESTIMATE at every call site."""
    if not isinstance(text, str):
        raise PolicyViolation("text must be a string")
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(messages: Sequence[ChatMessage]) -> int:
    """Estimate the input size of a bounded conversation."""
    total = 0
    for message in messages:
        total += 4  # per-message framing overhead estimate
        total += len(message.content) // CHARS_PER_TOKEN
    return max(1, total)


@dataclass(frozen=True)
class Budget:
    """Optional hard ceilings. ``None`` means the owner set no ceiling."""

    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None

    def validate(self) -> List[str]:
        errors: List[str] = []
        for name in ("max_input_tokens", "max_output_tokens", "max_total_tokens"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                errors.append(name + " must be a positive integer")
        if self.max_cost_usd is not None and (
            isinstance(self.max_cost_usd, bool) or not isinstance(self.max_cost_usd, (int, float))
            or not math.isfinite(self.max_cost_usd) or self.max_cost_usd <= 0
        ):
            errors.append("max_cost_usd must be a positive number")
        if self.max_input_tokens and self.max_total_tokens and self.max_total_tokens < self.max_input_tokens:
            errors.append("max_total_tokens must cover max_input_tokens")
        if self.max_output_tokens and self.max_total_tokens and self.max_total_tokens < self.max_output_tokens:
            errors.append("max_total_tokens must cover max_output_tokens")
        return errors

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise PolicyViolation("; ".join(sorted(set(errors))))


@dataclass
class BudgetLedger:
    """Per-task reservation and recorded usage, in this process."""

    ceiling: Budget = field(default_factory=Budget)
    _reserved: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def reserve(self, task_id: str, *, estimated_input: int, requested_output: int,
                ceiling: Optional[Budget] = None) -> Tuple[bool, str]:
        label = _bounded_id(task_id)
        if isinstance(estimated_input, bool) or not isinstance(estimated_input, int) or estimated_input < 0:
            raise PolicyViolation("estimated_input must be a non-negative integer")
        if isinstance(requested_output, bool) or not isinstance(requested_output, int) or requested_output < 1:
            raise PolicyViolation("requested_output must be a positive integer")
        ceiling = ceiling or self.ceiling
        ceiling.assert_valid()
        self._reserved[label] = {
            "estimated_input": estimated_input,
            "requested_output": requested_output,
            "observed_total": None,
            "observed_cost": None,
            "ceiling": ceiling,
        }
        if ceiling.max_input_tokens and estimated_input > ceiling.max_input_tokens:
            return False, "estimated_input_over_ceiling"
        if ceiling.max_total_tokens and estimated_input + requested_output > ceiling.max_total_tokens:
            return False, "estimated_total_over_ceiling"
        return True, ""

    def record(self, task_id: str, usage: Optional[Mapping[str, int]],
               cost_usd: Optional[float] = None) -> Tuple[bool, str]:
        """Recheck ceilings against actually reported usage."""
        label = _bounded_id(task_id)
        entry = self._reserved.get(label)
        if entry is None:
            raise PolicyViolation("task has no reservation")
        ceiling = entry.get("ceiling") or self.ceiling
        if usage:
            total = 0
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = usage.get(key)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PolicyViolation("usage values must be non-negative integers")
                total = max(total, value) if key == "total_tokens" else total
            if "total_tokens" in usage:
                total = usage["total_tokens"]
            else:
                total = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
            entry["observed_total"] = total
            if ceiling.max_total_tokens and total > ceiling.max_total_tokens:
                return False, "observed_total_over_ceiling"
            if ceiling.max_input_tokens and usage.get("input_tokens") is not None \
                    and usage["input_tokens"] > ceiling.max_input_tokens:
                return False, "observed_input_over_ceiling"
            if ceiling.max_output_tokens and usage.get("output_tokens") is not None \
                    and usage["output_tokens"] > ceiling.max_output_tokens:
                return False, "observed_output_over_ceiling"
        if cost_usd is not None:
            if isinstance(cost_usd, bool) or not isinstance(cost_usd, (int, float)) or not math.isfinite(cost_usd):
                raise PolicyViolation("cost_usd must be a finite number")
            entry["observed_cost"] = float(cost_usd)
            if ceiling.max_cost_usd and float(cost_usd) > ceiling.max_cost_usd:
                return False, "cost_over_ceiling"
        return True, ""

    def observed(self, task_id: str) -> Dict[str, Any]:
        entry = self._reserved.get(_bounded_id(task_id))
        if entry is None:
            raise PolicyViolation("task has no reservation")
        return dict(entry)


class CooldownTracker:
    """Bounded provider/model cooldowns after transient failures."""

    def __init__(self, seconds: float = 60.0) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 3600:
            raise PolicyViolation("cooldown seconds must be 1..3600")
        self.seconds = float(seconds)
        self._until: Dict[Tuple[str, str], float] = {}

    def cool(self, provider: str, model_id: str, *, now: Optional[float] = None, seconds: Optional[float] = None) -> None:
        import time

        stamp = time.time() if now is None else now
        duration = self.seconds if seconds is None else seconds
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 1 <= duration <= 3600:
            raise PolicyViolation("cooldown seconds must be 1..3600")
        self._until[(provider, model_id)] = stamp + float(duration)

    def available(self, provider: str, model_id: str, *, now: Optional[float] = None) -> bool:
        import time

        stamp = time.time() if now is None else now
        return stamp >= self._until.get((provider, model_id), 0.0)

    def active(self, *, now: Optional[float] = None) -> List[Tuple[str, str]]:
        import time

        stamp = time.time() if now is None else now
        return sorted(key for key, until in self._until.items() if until > stamp)


@dataclass(frozen=True)
class CompactionResult:
    messages: Tuple[ChatMessage, ...]
    dropped_turns: int
    estimated_input_tokens: int
    note: str = "heuristic_bound_not_semantic"


def compact(messages: Sequence[ChatMessage], *, max_chars: int, keep_last: int = 2) -> CompactionResult:
    """Deterministically bound a conversation.

    The system instruction and the most recent ``keep_last`` turns are always
    kept; older turns are dropped oldest first and counted. This is a heuristic
    bound, not a semantic summary.
    """
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 256 <= max_chars <= 1 << 20:
        raise PolicyViolation("max_chars must be 256..1048576")
    if isinstance(keep_last, bool) or not isinstance(keep_last, int) or not 1 <= keep_last <= 16:
        raise PolicyViolation("keep_last must be 1..16")
    ordered = list(messages)
    system = [m for m in ordered if m.role == "system"]
    rest = [m for m in ordered if m.role != "system"]
    kept: List[ChatMessage] = system[:1]
    used = sum(len(m.content) for m in kept)
    tail = rest[-keep_last:] if keep_last else []
    for message in tail:
        if used + len(message.content) > max_chars:
            raise PolicyViolation("even the most recent turns exceed the bound")
        kept.append(message)
        used += len(message.content)
    dropped = 0
    for message in reversed(rest[: len(rest) - len(tail)]):
        if used + len(message.content) <= max_chars:
            kept.insert(len(kept) - len(tail), message)
            used += len(message.content)
        else:
            dropped += 1
    kept.sort(key=lambda m: 0 if m.role == "system" else 1)
    return CompactionResult(messages=tuple(kept), dropped_turns=dropped,
                             estimated_input_tokens=estimate_message_tokens(kept))


def _bounded_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise PolicyViolation("task id must be a bounded non-empty string")
    return value
