"""Owner-approved policy axes (ADR-0002, ADR-0004).

Boru Core treats four domains as strictly orthogonal:

* ``optimization_mode``      AUTO / ECONOMY / BALANCED / PERFORMANCE / MANUAL
* ``inference_scope``        LOCAL_ONLY / CLOUD_ALLOWED
* ``execution_profile``      LOCAL_ISOLATED / HYBRID_PRIVATE /
                             CLOUD_SHELL_APPROVAL / CLOUD_SHELL_TRUSTED
* ``disclosure_policy``      MINIMUM_NECESSARY / SCOPED_APPROVED

No code path may widen more than one axis at a time.  ``with_optimization`` is
the only mutator exposed: changing an efficiency preset can never touch
inference, execution or disclosure rights.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

from .errors import ContractError

OPTIMIZATION_MODES: Tuple[str, ...] = ("AUTO", "ECONOMY", "BALANCED", "PERFORMANCE", "MANUAL")
INFERENCE_SCOPES: Tuple[str, ...] = ("LOCAL_ONLY", "CLOUD_ALLOWED")
EXECUTION_PROFILES: Tuple[str, ...] = (
    "LOCAL_ISOLATED",
    "HYBRID_PRIVATE",
    "CLOUD_SHELL_APPROVAL",
    "CLOUD_SHELL_TRUSTED",
)
DISCLOSURE_POLICIES: Tuple[str, ...] = ("MINIMUM_NECESSARY", "SCOPED_APPROVED")

#: Every sizing limit carries an upper as well as a lower bound, so a policy
#: can never widen a guard rail to an unbounded value.
MAX_RESULT_FIELDS_LIMIT = 32
MAX_RETRIES_LIMIT = 8
CLOUD_SHELL_PROFILES = frozenset({"CLOUD_SHELL_APPROVAL", "CLOUD_SHELL_TRUSTED"})
DISCLOSURE_LEVELS: Tuple[str, ...] = ("L0", "L1", "L2")

# Providers that only run on the local host.  Remote providers must be declared
# explicitly by the owner in the provider registry; Boru never guesses.
LOCAL_PROVIDERS = frozenset({"jan", "mock"})


@dataclass(frozen=True)
class Policy:
    """Immutable snapshot of the four policy axes.

    Safe defaults follow ADR-0002/ADR-0004: ``LOCAL_ISOLATED`` execution,
    ``MINIMUM_NECESSARY`` disclosure and **``LOCAL_ONLY`` inference**.  The
    runtime never starts cloud-enabled; an owner must change that axis
    deliberately.
    """

    optimization_mode: str = "AUTO"
    inference_scope: str = "LOCAL_ONLY"
    execution_profile: str = "LOCAL_ISOLATED"
    disclosure_policy: str = "MINIMUM_NECESSARY"

    # Execution / disclosure guard rails.
    cloud_shell_enabled: bool = False
    cloud_shell_sandbox_required: bool = True
    cloud_shell_live_consent_required: bool = True
    raw_tool_output_to_cloud: bool = False
    recipient_bound_consent_required: bool = True
    max_result_fields: int = 4

    # Sizing / fallback limits.
    max_agents: int = 6
    max_retries: int = 2
    cloud_fallback_enabled: bool = False

    def __post_init__(self) -> None:
        """Reject malformed policies at construction time."""
        self.assert_valid()

    def validate(self) -> list:
        """Return a list of policy violations; empty means consistent."""
        errors: list = []
        for name, value in (
            ("optimization_mode", self.optimization_mode),
            ("inference_scope", self.inference_scope),
            ("execution_profile", self.execution_profile),
            ("disclosure_policy", self.disclosure_policy),
        ):
            if not isinstance(value, str):
                errors.append(name + " must be a string")
        for name in (
            "cloud_shell_enabled",
            "cloud_shell_sandbox_required",
            "cloud_shell_live_consent_required",
            "raw_tool_output_to_cloud",
            "recipient_bound_consent_required",
            "cloud_fallback_enabled",
        ):
            if not isinstance(getattr(self, name), bool):
                errors.append(name + " must be a boolean")
        if self.optimization_mode not in OPTIMIZATION_MODES:
            errors.append("unknown optimization_mode")
        if self.inference_scope not in INFERENCE_SCOPES:
            errors.append("unknown inference_scope")
        if self.execution_profile not in EXECUTION_PROFILES:
            errors.append("unknown execution profile")
        if self.disclosure_policy not in DISCLOSURE_POLICIES:
            errors.append("unknown disclosure policy")
        if isinstance(self.max_agents, bool) or not isinstance(self.max_agents, int) or not 1 <= self.max_agents <= 6:
            errors.append("max_agents must be 1..6")
        if isinstance(self.max_result_fields, bool) or not isinstance(self.max_result_fields, int) \
                or not 1 <= self.max_result_fields <= MAX_RESULT_FIELDS_LIMIT:
            errors.append("max_result_fields must be 1..{}".format(MAX_RESULT_FIELDS_LIMIT))
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) \
                or not 0 <= self.max_retries <= MAX_RETRIES_LIMIT:
            errors.append("max_retries must be 0..{}".format(MAX_RETRIES_LIMIT))
        if self.inference_scope == "LOCAL_ONLY" and self.cloud_fallback_enabled:
            errors.append("LOCAL_ONLY forbids cloud fallback")
        if self.execution_profile in CLOUD_SHELL_PROFILES:
            if self.inference_scope != "CLOUD_ALLOWED":
                errors.append("cloud Shell profile requires CLOUD_ALLOWED")
            if not self.cloud_shell_enabled:
                errors.append("cloud Shell profile requires cloud_shell enabled")
            if not self.cloud_shell_sandbox_required or not self.cloud_shell_live_consent_required:
                errors.append("cloud Shell requires sandbox and independent owner consent")
        elif self.cloud_shell_enabled:
            errors.append("cloud_shell cannot be enabled in local-only Shell profile")
        if self.raw_tool_output_to_cloud:
            errors.append("raw_tool_output_to_cloud cannot be globally enabled")
        if not self.recipient_bound_consent_required:
            errors.append("recipient-bound consent required")
        return errors

    def assert_valid(self) -> None:
        """Raise ``ContractError`` when the policy is inconsistent."""
        errors = self.validate()
        if errors:
            raise ContractError("; ".join(errors))

    def with_optimization(self, mode: str) -> "Policy":
        """Return a copy with a new efficiency preset.

        The other three axes are copied verbatim; a bad preset is rejected
        rather than silently coerced.
        """
        if mode not in OPTIMIZATION_MODES:
            raise ContractError("unknown optimization_mode: " + str(mode))
        return replace(self, optimization_mode=mode)

    def allows_remote_inference(self) -> bool:
        return self.inference_scope == "CLOUD_ALLOWED"

    def allows_cloud_shell(self) -> bool:
        return (
            self.execution_profile in CLOUD_SHELL_PROFILES
            and self.cloud_shell_enabled
            and self.cloud_shell_sandbox_required
            and self.cloud_shell_live_consent_required
            and self.inference_scope == "CLOUD_ALLOWED"
        )

    def as_dict(self) -> dict:
        return {
            "optimization_mode": self.optimization_mode,
            "inference_scope": self.inference_scope,
            "execution_profile": self.execution_profile,
            "disclosure_policy": self.disclosure_policy,
        }
