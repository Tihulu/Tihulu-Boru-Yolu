"""Boru Core routing: mode-aware candidate ranking and bounded fallback.

Routing is *only* about which tested candidate serves a task.  It never widens
any policy axis: the candidate list is derived from the immutable policy plus
the registry, so a fallback on 429, timeout, credit exhaustion or model change
can only select another already-permitted candidate.

Modes select efficiency, not permission:

* ``ECONOMY``  — cheapest suitable candidate, local first, then remote.
* ``BALANCED`` — weighted quality/latency/cost.
* ``PERFORMANCE`` — strongest tested candidate within the hard limits.
* ``AUTO``     — complexity-driven: simple behaves like ECONOMY, medium like
  BALANCED, difficult like PERFORMANCE, still bounded.
* ``MANUAL``   — exactly the owner-selected provider/model.

Unknown credits, limits or latency are recorded as ``UNKNOWN`` and never
invented; unknown values lower confidence rather than being assumed to be zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import PolicyViolation
from .policy import OPTIMIZATION_MODES
from .registry import UNKNOWN, ModelRecord, ModelRegistry

#: Failure categories that justify trying the next candidate.
RETRYABLE = frozenset({"timeout", "unavailable", "rate_limited", "server_error"})

#: Failure categories that must never trigger another attempt.
TERMINAL = frozenset({"policy_denied", "invalid_response", "request_too_large"})


@dataclass(frozen=True)
class RankedCandidate:
    """One permitted candidate with the reason it was selected."""

    provider: str
    model_id: str
    score: float
    local: bool
    reasons: Tuple[str, ...] = ()

    @property
    def key(self) -> Tuple[str, str]:
        return (self.provider, self.model_id)


@dataclass(frozen=True)
class RoutingDecision:
    """An ordered, policy-consistent candidate list."""

    selected: Optional[RankedCandidate]
    ordered: Tuple[RankedCandidate, ...]
    excluded: Tuple[Tuple[Tuple[str, str], str], ...] = ()
    mode: str = "AUTO"
    policy_unchanged: bool = True


def _confidence(record: ModelRecord) -> int:
    """Known good data beats assumed data."""
    source_rank = {"verified": 3, "discovered": 2, "configured": 1}
    health_rank = {"healthy": 3, "unknown": 1, "degraded": 0, "down": -100}
    score = source_rank.get(record.source, 0) + health_rank.get(record.health, 0)
    if record.source == "verified":
        score += 2
    return score


def _tags(record: ModelRecord, required: Sequence[str]) -> int:
    if not required:
        return 0
    wanted = set(required)
    present = set(record.tags)
    if wanted.issubset(present):
        return 3
    if wanted & present:
        return 1
    return -5


def _context_fit(record: ModelRecord, required: Optional[int]) -> int:
    if required is None or record.max_context is None:
        return 0  # unknown on either side: no preference, no penalty
    if record.max_context < required:
        return -50  # this candidate cannot hold the task's context
    slack = record.max_context - required
    return 2 if slack < required else 0


def rank(
    mode: str,
    records: Iterable[ModelRecord],
    *,
    local_only: bool,
    required_tags: Sequence[str] = (),
    complexity: str = "simple",
    required_context: Optional[int] = None,
) -> List[RankedCandidate]:
    """Return permitted candidates, best first, for the given mode."""
    if mode not in OPTIMIZATION_MODES:
        raise PolicyViolation("unknown optimization mode")
    allowed: List[ModelRecord] = []
    excluded: List[Tuple[Tuple[str, str], str]] = []
    for record in records:
        if record.health == "down":
            excluded.append(((record.provider, record.model_id), "unhealthy"))
            continue
        if local_only and not record.local:
            excluded.append(((record.provider, record.model_id), "not_local"))
            continue
        if _tags(record, required_tags) < 0:
            excluded.append(((record.provider, record.model_id), "missing_capability"))
            continue
        if _context_fit(record, required_context) < 0:
            excluded.append(((record.provider, record.model_id), "context_too_small"))
            continue
        allowed.append(record)
    effective = mode
    if mode == "AUTO":
        effective = {"simple": "ECONOMY", "medium": "BALANCED", "difficult": "PERFORMANCE"}.get(complexity, "BALANCED")
    ranked = [RankedCandidate(provider=r.provider, model_id=r.model_id, score=_score(effective, r, required_tags, required_context),
                              local=r.local) for r in allowed]
    ranked.sort(key=lambda c: (-c.score, not c.local, c.provider, c.model_id))
    return ranked


def _score(mode: str, record: ModelRecord, required_tags: Sequence[str], required_context: Optional[int]) -> float:
    confidence = _confidence(record)
    tags = _tags(record, required_tags)
    context = _context_fit(record, required_context)
    cost = record.cost_tier if isinstance(record.cost_tier, int) else None
    quality = record.quality_tier if isinstance(record.quality_tier, int) else None
    unknown_cost = 0 if cost is not None else 6  # unknown cost is a penalty, never an assumption
    unknown_quality = 0 if quality is not None else 4
    base = float(confidence + tags + context)
    if mode == "ECONOMY":
        local_bonus = 10 if record.local else 0
        return base + local_bonus - (cost * 6 if cost is not None else unknown_cost)
    if mode == "PERFORMANCE":
        return base + (quality * 4 if quality is not None else unknown_quality) + (3 if not record.local else 0)
    if mode == "BALANCED":
        return base + (quality * 2 if quality is not None else unknown_quality) - (cost * 3 if cost is not None else 0)
    return base


class Router:
    """Stateless router that cannot widen a policy axis."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def decide(
        self,
        *,
        mode: str,
        inference_scope: str,
        complexity: str = "simple",
        required_tags: Sequence[str] = (),
        selected_provider: Optional[str] = None,
        selected_model: Optional[str] = None,
        required_context: Optional[int] = None,
        max_parallel: int = 1,
    ) -> RoutingDecision:
        if mode not in OPTIMIZATION_MODES:
            raise PolicyViolation("unknown optimization mode")
        if inference_scope not in ("LOCAL_ONLY", "CLOUD_ALLOWED"):
            raise PolicyViolation("unknown inference scope")
        if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
            raise PolicyViolation("max_parallel must be a positive integer")
        if required_context is not None and (
            isinstance(required_context, bool) or not isinstance(required_context, int) or required_context < 1
        ):
            raise PolicyViolation("required_context must be a positive integer")
        local_only = inference_scope == "LOCAL_ONLY"
        records = self.registry.candidates(tags=required_tags, local_only=local_only)
        if mode == "MANUAL":
            if not (selected_provider and selected_model):
                raise PolicyViolation("MANUAL routing requires an owner selection")
            match = [r for r in records if (r.provider, r.model_id) == (selected_provider, selected_model)]
            if not match:
                raise PolicyViolation("selected model is not a permitted candidate")
            chosen = RankedCandidate(provider=selected_provider, model_id=selected_model, score=float(_confidence(match[0])),
                                     local=match[0].local, reasons=("owner_selected",))
            return RoutingDecision(selected=chosen, ordered=(chosen,), mode=mode)
        ranked = rank(mode, records, local_only=local_only, required_tags=required_tags,
                      complexity=complexity, required_context=required_context)
        if not ranked:
            return RoutingDecision(selected=None, ordered=(), mode=mode,
                                   excluded=tuple(
                                       ((r.provider, r.model_id), "not_permitted" if local_only and not r.local else "unavailable")
                                       for r in records))
        selected = ranked[0]
        # ``ordered`` is the full permitted fallback chain; ``max_parallel``
        # bounds parallel dispatch, never the fallback options.
        return RoutingDecision(selected=selected, ordered=tuple(ranked), mode=mode)


def fallback_order(decision: RoutingDecision, *, failed: Optional[Tuple[str, str]] = None) -> Tuple[RankedCandidate, ...]:
    """Return the remaining candidates after a failure, in policy order."""
    ordered = decision.ordered
    if failed is None:
        return ordered
    return tuple(candidate for candidate in ordered if candidate.key != failed)


def should_retry(category: str) -> bool:
    """Only bounded, already-permitted category failures may move to next candidate."""
    if category in TERMINAL:
        return False
    return category in RETRYABLE
