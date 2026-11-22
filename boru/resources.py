"""Resource profiles: performance / balanced / resource-optimized / custom.

A resource profile is a **performance knob**, never an authorization axis. It
chooses how aggressively Boru Core holds or releases its own resource leases;
it cannot grant inference, execution, Shell or disclosure rights, and switching
it never widens any of the four policy axes (ADR-0002, ADR-0004).

What this module actually controls:

* ``max_agents`` / ``max_large_local_models`` — the logical-agent and
  large-local-model lease ceilings (bounded, as before);
* ``idle_eviction_seconds`` — how long a *kept-warm* model lease may sit idle
  before Boru releases it (0 disables eviction);
* ``keep_warm`` — whether a large local model stays open (lease held) after the
  task that used it, or is released immediately;
* owner-declared device budgets (``vram_budget_mb``) — hints for planning, not
  measurements.

What it cannot do by itself: release RAM or VRAM held by an external model
process. Boru Core releases its own lease and asks the provider to unload the
model; the provider hook exists (`ChatProvider.unload`), and a provider
without a documented lifecycle endpoint (Jan today, see
`docs/ROUTING_AND_RESOURCES.md`) refuses with ``unsupported_capability``
instead of pretending.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Tuple

from .errors import ConfigurationError

#: Logical agents are scheduling roles, never six concurrently loaded models.
#: The scheduler builds on this bound; it lives here so profiles and the
#: scheduler share one definition.
MAX_AGENTS = 6
#: A large-local-model lease may never exceed the measured-era bound of two.
MAX_LARGE_LOCAL_MODELS = 2
#: Idle eviction is bounded: from 60 seconds to one day, or disabled with 0.
MIN_EVICTION_SECONDS = 60
MAX_EVICTION_SECONDS = 86400
#: Device budgets are owner declarations, bounded to a sane range.
MAX_VRAM_BUDGET_MB = 65536


class ResourceMode(str, Enum):
    """The four resource profiles; ``CUSTOM`` uses owner-provided bounds."""

    PERFORMANCE = "PERFORMANCE"
    BALANCED = "BALANCED"
    RESOURCE_OPTIMIZED = "RESOURCE_OPTIMIZED"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class ResourceProfile:
    """One resource profile: lease ceilings, idle policy and device budgets."""

    mode: ResourceMode = ResourceMode.BALANCED
    max_agents: int = 4
    max_large_local_models: int = 1
    #: Seconds a kept-warm model lease may stay idle before release (0 = keep).
    idle_eviction_seconds: int = 900
    #: Hold a large-local-model lease open after the task that used it.
    keep_warm: bool = False
    #: Owner-declared planning budget for the discrete GPU, in MB.
    vram_budget_mb: int = 12288
    #: Owner-declared planning budget for shared (iGPU) memory, in MB.
    shared_memory_budget_mb: int = 16384

    _BOUNDS = ("max_agents", "max_large_local_models", "idle_eviction_seconds",
               "keep_warm", "vram_budget_mb", "shared_memory_budget_mb")

    def __post_init__(self) -> None:
        """Reject a malformed profile, and a named profile that was edited.

        A named profile has fixed bounds; an owner who wants different numbers
        uses ``CUSTOM`` (or ``with_overrides``, which relabels the result), so
        a silent half-edited preset is never possible.
        """
        self.assert_valid()
        if self.mode is ResourceMode.CUSTOM:
            return
        # ``PRESETS`` is still being built while the presets themselves are
        # constructed: the fixed-bounds check only applies afterwards.
        preset = globals().get("PRESETS", {}).get(self.mode)
        if preset is None:
            return
        for name in self._BOUNDS:
            if getattr(self, name) != getattr(preset, name):
                raise ConfigurationError(
                    "a named resource profile has fixed bounds; use CUSTOM or "
                    "with_overrides for " + name)

    def validate(self) -> list:
        errors: list = []
        if not isinstance(self.mode, ResourceMode):
            errors.append("unknown resource mode")
        if isinstance(self.max_agents, bool) or not isinstance(self.max_agents, int) \
                or not 1 <= self.max_agents <= MAX_AGENTS:
            errors.append("max_agents must be 1..{} logical agents".format(MAX_AGENTS))
        if isinstance(self.max_large_local_models, bool) or not isinstance(self.max_large_local_models, int) \
                or not 0 <= self.max_large_local_models <= MAX_LARGE_LOCAL_MODELS:
            errors.append("max_large_local_models must be 0..{}".format(MAX_LARGE_LOCAL_MODELS))
        if isinstance(self.idle_eviction_seconds, bool) or not isinstance(self.idle_eviction_seconds, int) \
                or not (self.idle_eviction_seconds == 0
                        or MIN_EVICTION_SECONDS <= self.idle_eviction_seconds <= MAX_EVICTION_SECONDS):
            errors.append("idle_eviction_seconds must be 0 or {}..{}".format(
                MIN_EVICTION_SECONDS, MAX_EVICTION_SECONDS))
        if not isinstance(self.keep_warm, bool):
            errors.append("keep_warm must be a boolean")
        for name in ("vram_budget_mb", "shared_memory_budget_mb"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_VRAM_BUDGET_MB:
                errors.append(name + " must be 0..{} MB".format(MAX_VRAM_BUDGET_MB))
        if self.mode is ResourceMode.CUSTOM and self.idle_eviction_seconds == 0 and not self.keep_warm:
            errors.append("a custom profile must either evict idle leases or keep models warm")
        return errors

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ConfigurationError("; ".join(errors))

    def evicts_idle(self) -> bool:
        """True when an idle kept-warm lease is released after the threshold."""
        return self.idle_eviction_seconds > 0

    def as_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "max_agents": self.max_agents,
            "max_large_local_models": self.max_large_local_models,
            "idle_eviction_seconds": self.idle_eviction_seconds,
            "keep_warm": self.keep_warm,
            "vram_budget_mb": self.vram_budget_mb,
            "shared_memory_budget_mb": self.shared_memory_budget_mb,
        }

    @classmethod
    def for_mode(cls, mode) -> "ResourceProfile":
        """The profile for a named mode; an edited copy is never returned."""
        return profile_for(mode)

    def with_overrides(self, **overrides) -> "ResourceProfile":
        """Apply owner overrides; the mode becomes ``CUSTOM`` for the result."""
        unknown = sorted(set(overrides) - set(self._BOUNDS))
        if unknown:
            raise ConfigurationError("unknown resource override: " + ", ".join(unknown))
        cleaned = {name: value for name, value in overrides.items() if value is not None}
        # an overridden profile is CUSTOM by definition: relabel before the
        # construction-time check runs, or the fixed-bounds check would refuse
        # its own result
        profile = replace(self, mode=ResourceMode.CUSTOM, **cleaned)
        profile.assert_valid()
        return profile


#: The three presets, sized for a 60 GB RAM host with a 16 GB discrete GPU and
#: a shared-memory iGPU.  Values are lease ceilings and budgets, never
#: measurements: a profile cannot make a device larger than it is.
PRESETS = {
    ResourceMode.PERFORMANCE: ResourceProfile(
        mode=ResourceMode.PERFORMANCE,
        max_agents=MAX_AGENTS,
        max_large_local_models=2,
        idle_eviction_seconds=0,
        keep_warm=True,
        vram_budget_mb=15360,
        shared_memory_budget_mb=24576,
    ),
    ResourceMode.BALANCED: ResourceProfile(
        mode=ResourceMode.BALANCED,
        max_agents=4,
        max_large_local_models=1,
        idle_eviction_seconds=900,
        keep_warm=False,
        vram_budget_mb=12288,
        shared_memory_budget_mb=16384,
    ),
    ResourceMode.RESOURCE_OPTIMIZED: ResourceProfile(
        mode=ResourceMode.RESOURCE_OPTIMIZED,
        max_agents=2,
        max_large_local_models=1,
        idle_eviction_seconds=MIN_EVICTION_SECONDS,
        keep_warm=False,
        vram_budget_mb=8192,
        shared_memory_budget_mb=8192,
    ),
}

DEFAULT_MODE = ResourceMode.BALANCED


def profile_for(mode, **overrides) -> ResourceProfile:
    """Return the profile for a mode, with optional owner overrides."""
    if isinstance(mode, str):
        try:
            mode = ResourceMode(mode.strip().upper())
        except ValueError:
            raise ConfigurationError("unknown resource mode: " + str(mode))
    if not isinstance(mode, ResourceMode):
        raise ConfigurationError("resource mode must be a ResourceMode")
    if mode is ResourceMode.CUSTOM:
        if not overrides:
            raise ConfigurationError("a custom profile requires explicit bounds")
        return ResourceProfile(mode=ResourceMode.CUSTOM).with_overrides(**overrides)
    return PRESETS[mode]


def detect_swap() -> Tuple[Optional[int], Optional[int]]:
    """Read swap total and free space from ``/proc/meminfo`` (Linux).

    Swap is reported, never tuned: swapping behaviour is the owner's host
    configuration, and Boru Core only makes its own footprint smaller by
    releasing its leases.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            fields = {}
            for line in handle:
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                value = parts[1].strip().split(" ", 1)[0]
                if value.isdigit():
                    fields[parts[0]] = int(value)
    except OSError:
        return None, None
    total = fields.get("SwapTotal")
    free = fields.get("SwapFree")
    if total is None or free is None:
        return None, None
    return int(total // 1024), int(free // 1024)  # kB -> MB


def detect_memory() -> Tuple[Optional[int], Optional[int]]:
    """Read total and available RAM from ``/proc/meminfo`` (Linux).

    Returns ``(None, None)`` where the information is unavailable; a host is
    never guessed from a device inventory.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            fields = {}
            for line in handle:
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                value = parts[1].strip().split(" ", 1)[0]
                if value.isdigit():
                    fields[parts[0]] = int(value)
    except OSError:
        return None, None
    total = fields.get("MemTotal")
    available = fields.get("MemAvailable", fields.get("MemFree"))
    if total is None or available is None:
        return None, None
    return int(total // 1024), int(available // 1024)  # kB -> MB


def memory_pressure() -> Optional[float]:
    """Available RAM as a share of total, or ``None`` when undetectable."""
    total, available = detect_memory()
    if not total or available is None or available < 0 or total <= 0:
        return None
    share = available / float(total)
    if not 0.0 <= share <= 1.0:
        return None
    return round(share, 4)
