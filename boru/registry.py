"""Local model/provider registry with honest, evidence-based metadata.

Every entry records where the entry came from (``discovered`` from a live
endpoint, ``configured`` by the owner, ``verified`` by a passing test) and
which model was *actually* observed.  Capacity, credits and limits that Boru
cannot observe are stored as the literal string ``UNKNOWN`` rather than being
invented (docs/ROUTING_AND_RESOURCES.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import PolicyViolation

UNKNOWN = "UNKNOWN"
MODEL_SOURCES: Tuple[str, ...] = ("discovered", "configured", "verified")
HEALTH_STATES: Tuple[str, ...] = ("unknown", "healthy", "degraded", "down")


@dataclass(frozen=True)
class ModelRecord:
    """One authorized model candidate."""

    provider: str
    model_id: str
    source: str = "configured"
    health: str = "unknown"
    max_context: Optional[int] = None
    tags: Tuple[str, ...] = ()
    #: Owner-declared or measured ranking hints. ``None`` means UNKNOWN and is
    #: never replaced with an assumed value (docs/ROUTING_AND_RESOURCES.md).
    cost_tier: Optional[int] = None
    quality_tier: Optional[int] = None
    last_test_at: Optional[str] = None
    #: Locality is an owner-supplied fact about the endpoint, never inferred
    #: from a provider name.  Default: not local.
    local: bool = False
    credits: str = UNKNOWN
    last_error_kind: Optional[str] = None

    def __post_init__(self) -> None:
        """Reject malformed metadata at construction time."""
        self.assert_valid()

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            from .errors import ContractError

            raise ContractError("; ".join(errors))

    def validate(self) -> list:
        errors: list = []
        if not self.provider.strip() or not self.model_id.strip():
            errors.append("provider and model_id are required")
        if self.source not in MODEL_SOURCES:
            errors.append("unknown model source")
        if self.health not in HEALTH_STATES:
            errors.append("unknown health state")
        for name in ("cost_tier", "quality_tier"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9):
                errors.append(name + " must be an integer between 0 and 9")
        if self.max_context is not None and (isinstance(self.max_context, bool) or not isinstance(self.max_context, int) or self.max_context < 1):
            errors.append("max_context must be a positive integer")
        for label in ("tags",):
            items = getattr(self, label)
            if not isinstance(items, tuple) or any(not isinstance(i, str) or not i.strip() or len(i) > 64 for i in items):
                errors.append(label + " must be a tuple of bounded non-empty strings")
        return errors


def _score(record: ModelRecord, required_tags: Sequence[str]) -> int:
    """Mode-agnostic ranking: verified > discovered > configured, health desc."""
    source_rank = {"verified": 3, "discovered": 2, "configured": 1}
    health_rank = {"healthy": 3, "unknown": 1, "degraded": 0, "down": -100}
    score = source_rank.get(record.source, 0) + health_rank.get(record.health, 0)
    tags = set(record.tags)
    if required_tags and not tags.issuperset(set(required_tags)):
        score -= 5
    return score


class ModelRegistry:
    """In-memory registry of authorized providers and models."""

    def __init__(self, records: Iterable[ModelRecord] = ()) -> None:
        self._records: Dict[Tuple[str, str], ModelRecord] = {}
        for record in records:
            self.register(record)

    def register(self, record: ModelRecord) -> ModelRecord:
        errors = record.validate()
        if errors:
            from .errors import ContractError

            raise ContractError("; ".join(errors))
        self._records[(record.provider, record.model_id)] = record
        return record

    def upsert_from_discovery(self, provider: str, model_ids: Iterable[str]) -> List[ModelRecord]:
        """Record models actually observed on a live endpoint."""
        added: List[ModelRecord] = []
        for model_id in model_ids:
            key = (provider, model_id)
            if key in self._records:
                existing = self._records[key]
                self._records[key] = ModelRecord(
                    provider=existing.provider,
                    model_id=existing.model_id,
                    source=existing.source,
                    health="healthy",
                    max_context=existing.max_context,
                    tags=existing.tags,
                    cost_tier=existing.cost_tier,
                    quality_tier=existing.quality_tier,
                    last_test_at=existing.last_test_at,
                    local=existing.local,
                    credits=existing.credits,
                )
            else:
                self.register(
                    ModelRecord(provider=provider, model_id=model_id, source="discovered", health="healthy",
                                local=provider in ("jan", "mock"))
                )
            added.append(self._records[key])
        return added

    def get(self, provider: str, model_id: str) -> Optional[ModelRecord]:
        return self._records.get((provider, model_id))

    def all(self) -> List[ModelRecord]:
        return sorted(self._records.values(), key=lambda r: (r.provider, r.model_id))

    def mark_health(self, provider: str, model_id: str, health: str, error_kind: Optional[str] = None) -> None:
        if health not in HEALTH_STATES:
            from .errors import ContractError

            raise ContractError("unknown health state: " + str(health))
        if error_kind is not None and (not isinstance(error_kind, str) or len(error_kind) > 64):
            from .errors import ContractError

            raise ContractError("error kind must be a bounded string")
        record = self._records.get((provider, model_id))
        if record is None:
            from .errors import ContractError

            raise ContractError("unknown model: {}/{}".format(provider, model_id))
        self._records[(provider, model_id)] = ModelRecord(
            provider=record.provider,
            model_id=record.model_id,
            source=record.source,
            health=health,
            max_context=record.max_context,
            tags=record.tags,
            cost_tier=record.cost_tier,
            quality_tier=record.quality_tier,
            last_test_at=record.last_test_at,
            local=record.local,
            credits=record.credits,
            last_error_kind=error_kind,
        )

    def mark_tested(self, provider: str, model_id: str, at: str) -> None:
        record = self._records.get((provider, model_id))
        if record is None:
            from .errors import ContractError

            raise ContractError("unknown model: {}/{}".format(provider, model_id))
        self._records[(provider, model_id)] = ModelRecord(
            provider=record.provider,
            model_id=record.model_id,
            source="verified",
            health="healthy",
            max_context=record.max_context,
            tags=record.tags,
            cost_tier=record.cost_tier,
            quality_tier=record.quality_tier,
            last_test_at=at,
            local=record.local,
            credits=record.credits,
            last_error_kind=None,
        )

    def candidates(self, tags: Sequence[str] = (), local_only: bool = False) -> List[ModelRecord]:
        records = [r for r in self._records.values() if r.health != "down"]
        if local_only:
            records = [r for r in records if r.local]
        if tags:
            # Capability tags must ALL match; a partial match is not a match.
            required = set(tags)
            records = [r for r in records if set(r.tags).issuperset(required)]
        return sorted(records, key=lambda r: (-_score(r, tags), r.provider, r.model_id))

    def select(self, mode: str, inference_scope: str, tags: Sequence[str] = ()) -> List[ModelRecord]:
        """Return ranked candidates permitted by the current policy.

        ``LOCAL_ONLY`` removes every non-local candidate; the result may be
        empty, which callers must treat as HOLD rather than widening scope.
        """
        if inference_scope not in ("LOCAL_ONLY", "CLOUD_ALLOWED"):
            raise PolicyViolation("unknown inference_scope")
        local_only = inference_scope == "LOCAL_ONLY"
        return self.candidates(tags=tags, local_only=local_only)

    def providers(self) -> Set[str]:
        return {record.provider for record in self._records.values()}
