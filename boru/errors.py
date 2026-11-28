"""Typed error hierarchy for Boru Core.

Every failure carries a stable machine-readable ``kind`` so callers can branch
on the failure class without parsing human text.  Messages are safe to record
in a local audit log: they never embed private payloads.
"""
from __future__ import annotations


class BoruError(Exception):
    """Base class for every Boru Core failure."""

    kind = "boru_error"


class ContractError(BoruError):
    """A typed contract (task envelope, result, config) is malformed."""

    kind = "contract_error"


class PolicyViolation(BoruError):
    """A requested action conflicts with the owner-approved policy axes."""

    kind = "policy_violation"


class InvalidTransition(BoruError):
    """An illegal task state transition was requested."""

    kind = "invalid_transition"


class DuplicateTask(BoruError):
    """The same idempotency key was submitted twice."""

    kind = "duplicate_task"


class QueueFull(BoruError):
    """The bounded task queue refuses more work."""

    kind = "queue_full"


class BudgetExceeded(BoruError):
    """A hard token or cost ceiling was reached."""

    kind = "budget_exceeded"


class ProviderUnavailable(BoruError):
    """No authorized provider could serve the request."""

    kind = "provider_unavailable"


class VerificationError(BoruError):
    """A result failed the mandatory verification gate."""

    kind = "verification_error"


class ConfigurationError(BoruError):
    """Boru configuration is missing or inconsistent."""

    kind = "configuration_error"


class ConnectorDenied(BoruError):
    """A repository operation was refused by the grant boundary."""

    kind = "connector_denied"


class StoreError(BoruError):
    """The local task state store is missing, corrupt, contended or full."""

    kind = "store_error"
