"""Boru Core Privacy Bridge gate (P5 source slice).

This is a **deterministic, fail-closed release gate**, not a broker and not a
security boundary.  It decides which typed fields may leave the local
trust boundary for one named recipient, and refuses everything else:

* only the allowlisted field names for the requested level may be released;
* raw host data (`raw_stdout`, paths, environment, credentials, file bodies)
  is refused at every level, always;
* an L2 excerpt needs an explicit, recipient-bound, field-scoped, expiring
  owner grant, otherwise the result is a denial — never a silent fallback;
* a missing, malformed, replayed or expired grant denies.

Independent OS-level isolation, authenticated workers and broker hardening are
**not** implemented here and must be reviewed before any live disclosure.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from .errors import PolicyViolation
from .policy import DISCLOSURE_LEVELS
from .types import FORBIDDEN_RESULT_KEYS

#: Level definitions: what each level may carry.
#: Level allowlists, matching docs/PRIVACY_BRIDGE.md: L0 is boolean/status/count,
#: L1 is narrowly required non-sensitive detail, L2 is a protected excerpt.
#: The typed fields produced by boru.executor are mapped onto these levels:
#: booleans and counts stay L0, bounded metadata (size, line count) is L1.
LEVEL_FIELDS: Dict[str, Tuple[str, ...]] = {
    "L0": ("status", "count", "passed", "failed", "state", "error_category",
           "exists", "entry_count", "type"),
    "L1": ("dependency_name", "package_name", "operation_alias", "model_alias", "provider_alias",
           "size", "line_count"),
    "L2": ("excerpt",),
}

MAX_FIELDS = 8
MAX_VALUE_CHARS = 512
MAX_DEPTH = 2
GRANT_TTL_SECONDS = 900


class Level(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class GateDecision(str, Enum):
    RELEASE = "release"
    DENY = "deny"
    HOLD = "hold"


@dataclass(frozen=True)
class DisclosureRequest:
    """One typed release request, shaped before any local data is acquired."""

    task_id: str
    recipient: str
    level: str
    fields: Tuple[str, ...]
    payload: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.task_id, str) or not self.task_id.strip() or len(self.task_id) > 128:
            errors.append("task_id must be a bounded non-empty string")
        if not isinstance(self.recipient, str) or not self.recipient.strip() or len(self.recipient) > 128:
            errors.append("recipient must be a bounded non-empty string")
        if self.level not in DISCLOSURE_LEVELS:
            errors.append("unknown disclosure level")
        if not isinstance(self.fields, tuple) or not self.fields:
            errors.append("fields must be a non-empty tuple")
        elif len(self.fields) > MAX_FIELDS or any(not isinstance(f, str) or not f.strip() or len(f) > 64 for f in self.fields):
            errors.append("fields must be bounded non-empty names")
        if len(set(self.fields)) != len(self.fields):
            errors.append("duplicate field names")
        return errors


def _value_error(value: Any, depth: int = 0) -> Optional[str]:
    """Reject anything that is not a bounded boolean, count or short enum string."""
    if depth > MAX_DEPTH:
        return "payload is nested too deeply"
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 10 ** 12:
            return "count is out of the bounded range"
        return None
    if isinstance(value, str):
        if len(value) > MAX_VALUE_CHARS:
            return "string exceeds the bounded length"
        if any(character in value for character in ("\n", "\r", "\x00")):
            return "string contains control characters"
        return None
    if isinstance(value, Mapping):
        if len(value) > MAX_FIELDS:
            return "object has too many keys"
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 64:
                return "object key is oversized"
            error = _value_error(item, depth + 1)
            if error:
                return error
        return None
    return "unsupported payload type"


LEVEL_RANK = {"L0": 0, "L1": 1, "L2": 2}
#: The same nonce bound the persistent store uses, so both stores behave alike.
MAX_NONCES = 8192


class ConsentStore:
    """In-memory, single-process owner-consent records (replay protected).

    A grant binds recipient, task, field and **level**: a weaker grant never
    authorizes a wider disclosure, whatever the endpoint asks for.
    """

    def __init__(self) -> None:
        self._grants: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        #: used nonce -> the expiry of the grant that carried it
        self._used_nonces: Dict[str, float] = {}

    def grant(self, *, grant_id: str, recipient: str, task_id: str, field_name: str,
              alias: Optional[str] = None, level: str, expires_at: float,
              nonce: str) -> None:
        if level not in DISCLOSURE_LEVELS:
            raise PolicyViolation("unknown disclosure level")
        # The alias is mandatory and bound, exactly as in the persistent store:
        # a grant without one would cover every resource.
        if not isinstance(alias, str) or not alias.strip() or len(alias) > 64:
            raise PolicyViolation("alias must be a bounded non-empty string")
        for name, value, limit in (("grant_id", grant_id, 128), ("recipient", recipient, 128),
                                    ("task_id", task_id, 128), ("field_name", field_name, 64),
                                    ("nonce", nonce, 64)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise PolicyViolation(name + " must be a bounded non-empty string")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) or not math.isfinite(expires_at):
            raise PolicyViolation("expires_at must be a finite timestamp")
        key = (grant_id, recipient, task_id, field_name)
        if key in self._grants:
            # A grant id is immutable: revocation cannot be reset by reissue.
            raise PolicyViolation("duplicate grant identifier")
        self._grants[key] = {"level": level, "expires_at": expires_at, "nonce": nonce,
                             "alias": alias, "revoked": False}

    def _retain(self, nonce: str, now: float) -> bool:
        """A used nonce outlives its grant; past the bound the store refuses.

        The bound is the same one the persistent store uses, so the in-memory
        store cannot grow without limit, and a nonce whose grant is still live
        is never evicted to make room.
        """
        expired = [nonce for nonce, until in self._used_nonces.items() if until <= now]
        for nonce in expired:
            self._used_nonces.pop(nonce, None)
        if len(self._used_nonces) > MAX_NONCES:
            # Roll this insert back rather than evict a live nonce to make room.
            self._used_nonces.pop(nonce, None)
            return False
        return True

    def revoke(self, grant_id: str) -> None:
        for key, record in self._grants.items():
            if key[0] == grant_id:
                record["revoked"] = True
                record["expires_at"] = 0.0

    def check(self, *, grant_id: str, recipient: str, task_id: str, field_name: str,
              nonce: str, alias: str, level: str = "L0", now: Optional[float] = None) -> bool:
        """A grant matches only if recipient, task, field, **alias**, expiry,
        nonce and the requested **level** all match (a weaker grant never covers
        wider, and a grant for one resource never covers another)."""
        if not isinstance(alias, str) or not alias.strip():
            return False
        record = self._grants.get((grant_id, recipient, task_id, field_name))
        if record is None or record["revoked"]:
            return False
        if record["nonce"] != nonce or nonce in self._used_nonces:
            return False
        if record["alias"] != alias:
            return False
        stamp = now if now is not None else time.time()
        if stamp >= record["expires_at"]:
            return False
        if LEVEL_RANK[level] > LEVEL_RANK[record["level"]]:
            return False
        self._used_nonces[nonce] = record["expires_at"]
        return self._retain(nonce, stamp)


class DisclosureGate:
    """Fail-closed typed release gate."""

    def __init__(self, policy_policy: str, *, max_result_fields: int = 4, allow_raw: bool = False,
                 audit=None) -> None:
        self.audit = audit
        if policy_policy not in ("MINIMUM_NECESSARY", "SCOPED_APPROVED"):
            raise PolicyViolation("unknown disclosure policy")
        if isinstance(max_result_fields, bool) or not isinstance(max_result_fields, int) or not 1 <= max_result_fields <= 32:
            raise PolicyViolation("max_result_fields must be 1..32")
        self.disclosure_policy = policy_policy
        self.max_result_fields = max_result_fields
        self.allow_raw = bool(allow_raw)

    def classify(self, request: DisclosureRequest) -> Tuple[GateDecision, List[str], Optional[str]]:
        """Return (decision, released_field_names, reason)."""
        problems = request.validate()
        if problems:
            self._record(request, "malformed_request")
            return GateDecision.DENY, (), "malformed_request"
        if request.level == "L2" and self.disclosure_policy != "SCOPED_APPROVED":
            return GateDecision.DENY, (), "policy_requires_scoped_approved"
        allowed = set(LEVEL_FIELDS[request.level])
        # Never release a private-carrying field, whatever the level.
        forbidden = set(request.fields) & FORBIDDEN_RESULT_KEYS
        if forbidden:
            return GateDecision.DENY, (), "private_field_refused"
        unknown = [name for name in request.fields if name not in allowed]
        if unknown:
            return GateDecision.DENY, (), "field_not_allowed_for_level"
        if len(request.fields) > self.max_result_fields:
            return GateDecision.DENY, (), "max_result_fields_exceeded"
        for name in request.fields:
            if name not in request.payload:
                return GateDecision.HOLD, (), "field_unavailable"
            error = _value_error(request.payload[name])
            if error:
                return GateDecision.DENY, (), "payload_rejected"
        if request.level == "L2":
            grant_id = request.payload.get("grant_id")
            nonce = request.payload.get("nonce")
            if not isinstance(grant_id, str) or not isinstance(nonce, str):
                return GateDecision.DENY, (), "missing_grant"
        return GateDecision.RELEASE, tuple(request.fields), ""

    def _record(self, request: DisclosureRequest, reason: str) -> None:
        if self.audit is not None:
            self.audit.record("disclosure", request.task_id, reason, request.level)

    def release(self, request: DisclosureRequest, consent: Optional[ConsentStore] = None,
                now: Optional[float] = None) -> Tuple[GateDecision, Dict[str, Any], Optional[str]]:
        """Release the minimum typed payload; anything else is refused."""
        decision, fields, reason = self.classify(request)
        if decision is not GateDecision.RELEASE:
            self._record(request, reason)
            return decision, {}, reason
        payload = {name: request.payload[name] for name in fields}
        if request.level == "L2":
            grant_id = request.payload.get("grant_id")
            nonce = request.payload.get("nonce")
            if consent is None:
                return GateDecision.DENY, {}, "consent_store_unavailable"
            if not consent.check(grant_id=grant_id, recipient=request.recipient,
                                 task_id=request.task_id, field_name="excerpt", nonce=nonce,
                                 alias=request.payload.get("alias", ""),
                                 level=request.level, now=now):
                return GateDecision.DENY, {}, "grant_invalid"
        if self.allow_raw:
            return GateDecision.DENY, (), "raw_release_refused"
        return GateDecision.RELEASE, payload, ""
