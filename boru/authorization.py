"""Request-bound authorization receipts (review finding F01/F08/F09).

A receipt is a capability the broker issues and the worker verifies. It binds
the task, operation, resource alias, worker, consent grant, requested fields
and expiry, and carries an authentication tag derived from a shared
authorization key. The worker refuses a receipt that is not authentic, not
``allow``, expired, or bound to a different request.

The authorization key is derived from the worker secret when a worker registry
is used, so a broker process and a worker process that both know the secret can
verify the same receipt without transferring it. The tag is not a secret; the
key is.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

from .errors import PolicyViolation

RECEIPT_REVISION = 1

#: A receipt names a resource only by this opaque token form, never a path.
TOKEN_RE = re.compile("^r-[0-9a-f]{16}$")


def _canonical(*parts: Sequence[Any]) -> bytes:
    return json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def derive_key(secret: str) -> bytes:
    """Derive an authorization key from a worker secret (never stored)."""
    if not isinstance(secret, str) or len(secret) != 64:
        raise PolicyViolation("authorization key requires a 256-bit worker secret")
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), b"boru-authorization-key-v1", 4096)


def sign(key: bytes, *, task_id: str, operation: str, alias: str, worker_id: str, grant_id: str,
         nonce: str, expires_at: float, fields: Sequence[str], target: str = "",
         issued_at: float = 0.0) -> str:
    """Authenticate exactly the fields the receipt carries.

    ``issued_at`` is part of the signed payload so no field a receipt carries can
    be rewritten in transit without failing the tag. It is rounded to the same
    precision as ``expires_at`` so a float re-encode cannot change the tag.
    """
    payload = _canonical([RECEIPT_REVISION, task_id, operation, alias, worker_id, grant_id,
                          nonce, round(float(expires_at), 6), list(fields), target,
                          round(float(issued_at), 6)])
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AuthorizationReceipt:
    """One authorization decision, verified by the worker."""

    receipt_id: str
    operation: str
    resource_alias: str
    task_id: str
    worker_id: str
    grant_id: str
    issued_at: float
    expires_at: float
    nonce: str
    policy_revision: int = RECEIPT_REVISION
    decision: str = "allow"
    allowed_fields: Tuple[str, ...] = ()
    target: str = ""
    authentication_tag: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """A wire-safe view: identifiers only, never a path or a payload."""
        return {
            "receipt_id": self.receipt_id,
            "operation": self.operation,
            "resource_alias": self.resource_alias,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "grant_id": self.grant_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "policy_revision": self.policy_revision,
            "decision": self.decision,
            "allowed_fields": list(self.allowed_fields),
            "target": self.target,
            "authentication_tag": self.authentication_tag,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "AuthorizationReceipt":
        """Rebuild a receipt from a wire view, refusing anything malformed."""
        if not isinstance(payload, dict):
            raise PolicyViolation("receipt payload must be an object")
        fields = payload.get("allowed_fields", ())
        if fields is None or isinstance(fields, (str, bytes)) or not isinstance(fields, (list, tuple)):
            raise PolicyViolation("receipt fields must be a list")
        receipt = cls(
            receipt_id=payload.get("receipt_id", ""),
            operation=payload.get("operation", ""),
            resource_alias=payload.get("resource_alias", ""),
            task_id=payload.get("task_id", ""),
            worker_id=payload.get("worker_id", ""),
            grant_id=payload.get("grant_id", ""),
            issued_at=payload.get("issued_at", 0),
            expires_at=payload.get("expires_at", 0),
            nonce=payload.get("nonce", ""),
            policy_revision=payload.get("policy_revision", 0),
            decision=payload.get("decision", ""),
            allowed_fields=tuple(str(f) for f in fields),
            target=payload.get("target", "") or "",
            authentication_tag=payload.get("authentication_tag", ""),
        )
        if receipt.validate():
            raise PolicyViolation("receipt payload is malformed")
        return receipt

    def validate(self) -> list:
        errors: list = []
        for name, limit in (("receipt_id", 96), ("operation", 64), ("resource_alias", 64),
                            ("task_id", 128), ("worker_id", 64), ("grant_id", 128),
                            ("nonce", 64), ("allowed_fields", 8)):
            value = getattr(self, name)
            if name == "allowed_fields":
                if not isinstance(value, tuple) or len(value) > limit:
                    errors.append("allowed_fields must be a bounded tuple")
                continue
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(name + " must be a bounded non-empty string")
        if self.decision != "allow":
            errors.append("receipt must be an allow decision")
        if self.policy_revision != RECEIPT_REVISION:
            errors.append("unsupported receipt revision")
        if not isinstance(self.authentication_tag, str) or len(self.authentication_tag) != 64:
            errors.append("receipt authentication tag is missing")
        if not isinstance(self.target, str) or len(self.target) > 64:
            errors.append("target must be a bounded string")
        # The resource is an opaque token: a path can never ride in a receipt.
        if not isinstance(self.resource_alias, str) or not TOKEN_RE.match(self.resource_alias):
            errors.append("resource must be named by an opaque token")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(name + " must be a finite number")
        if not errors and self.expires_at <= self.issued_at:
            errors.append("expires_at must follow issued_at")
        return errors

    def verify(self, key: bytes, *, now: float, requested_fields: Sequence[str]) -> None:
        """Raise ``PolicyViolation`` unless this receipt is authentic and current."""
        errors = self.validate()
        if errors:
            raise PolicyViolation("receipt invalid: " + "; ".join(sorted(set(errors))))
        if now >= self.expires_at:
            raise PolicyViolation("receipt expired")
        requested = tuple(requested_fields)
        if set(requested) - set(self.allowed_fields):
            raise PolicyViolation("requested fields exceed the receipt")
        expected = sign(key, task_id=self.task_id, operation=self.operation,
                        alias=self.resource_alias, worker_id=self.worker_id,
                        grant_id=self.grant_id, nonce=self.nonce, expires_at=self.expires_at,
                        fields=self.allowed_fields, target=self.target,
                        issued_at=self.issued_at)
        if not hmac.compare_digest(expected, self.authentication_tag):
            raise PolicyViolation("receipt authentication failed")
