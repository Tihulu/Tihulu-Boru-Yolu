"""Resource profiles: lease bounds, idle policy, keep-warm, host memory.

A resource profile is a performance knob, never an authorization axis: these
tests assert that changing a profile can never widen a policy bound, that idle
eviction is usage-safe, and that the keep-warm lease is released only after the
profile's own threshold.
"""
import time
import unittest

from boru.config import CoreConfig, ProviderConfig
from boru.errors import ConfigurationError
from boru.policy import Policy
from boru.resources import (
    MAX_AGENTS,
    PRESETS,
    ResourceMode,
    ResourceProfile,
    detect_memory,
    detect_swap,
    memory_pressure,
    profile_for,
)
from boru.scheduler import AgentScheduler, AgentSpec


class ProfileTableTests(unittest.TestCase):
    def test_four_modes_and_their_bounds(self):
        performance = profile_for(ResourceMode.PERFORMANCE)
        balanced = profile_for(ResourceMode.BALANCED)
        optimized = profile_for(ResourceMode.RESOURCE_OPTIMIZED)
        self.assertEqual(MAX_AGENTS, performance.max_agents)
        self.assertTrue(performance.keep_warm)
        self.assertFalse(performance.evicts_idle())
        self.assertLess(optimized.max_agents, balanced.max_agents)
        self.assertLess(optimized.idle_eviction_seconds, balanced.idle_eviction_seconds)
        self.assertFalse(optimized.keep_warm)

    def test_a_named_profile_cannot_be_half_edited(self):
        with self.assertRaises(ConfigurationError):
            ResourceProfile(mode=ResourceMode.PERFORMANCE, max_agents=3)
        # overrides relabel the result as CUSTOM instead
        custom = PRESETS[ResourceMode.PERFORMANCE].with_overrides(max_agents=2)
        self.assertEqual(ResourceMode.CUSTOM, custom.mode)
        self.assertEqual(2, custom.max_agents)

    def test_bad_bounds_are_refused(self):
        for bad in (dict(idle_eviction_seconds=30), dict(max_agents=MAX_AGENTS + 1),
                    dict(max_large_local_models=3), dict(vram_budget_mb=10 ** 9),
                    dict(keep_warm="yes")):
            with self.assertRaises(ConfigurationError):
                ResourceProfile(mode=ResourceMode.CUSTOM, **bad)
        # a custom profile must either evict idle leases or keep models warm
        with self.assertRaises(ConfigurationError):
            ResourceProfile(mode=ResourceMode.CUSTOM, idle_eviction_seconds=0, keep_warm=False)

    def test_profile_never_widens_the_policy_ceiling(self):
        scheduler = AgentScheduler(Policy(max_agents=2),
                                   profile=ResourceProfile.for_mode(ResourceMode.PERFORMANCE))
        self.assertEqual(2, scheduler.max_agents)
        with self.assertRaises(Exception):
            AgentScheduler(Policy(max_agents=2), max_agents=6)


class IdleEvictionTests(unittest.TestCase):
    def test_idle_kept_warm_lease_is_evicted(self):
        profile = ResourceProfile.for_mode(ResourceMode.BALANCED)
        scheduler = AgentScheduler(Policy(max_agents=6), profile=profile)
        spec = AgentSpec(agent_id="a1", task_id="t1", large_local_model=True)
        scheduler.add(spec)
        scheduler.acquire(spec)
        scheduler.release("t1", keep_model=True)
        self.assertTrue(scheduler.leases.holds("large_local_models", "t1"))
        stale = time.time() - profile.idle_eviction_seconds - 1
        scheduler.leases.touch("large_local_models", "t1", stale)
        self.assertEqual(["t1"], scheduler.evict_idle())
        self.assertFalse(scheduler.leases.holds("large_local_models", "t1"))

    def test_a_recently_used_lease_is_not_evicted(self):
        scheduler = AgentScheduler(Policy(max_agents=6),
                                   profile=ResourceProfile.for_mode(ResourceMode.BALANCED))
        spec = AgentSpec(agent_id="a2", task_id="t2", large_local_model=True)
        scheduler.add(spec)
        scheduler.acquire(spec)
        scheduler.release("t2", keep_model=True)
        self.assertEqual([], scheduler.evict_idle())
        self.assertTrue(scheduler.leases.holds("large_local_models", "t2"))

    def test_performance_keeps_a_warm_lease_forever(self):
        scheduler = AgentScheduler(Policy(max_agents=6),
                                   profile=ResourceProfile.for_mode(ResourceMode.PERFORMANCE))
        spec = AgentSpec(agent_id="a3", task_id="t3", large_local_model=True)
        scheduler.add(spec)
        scheduler.acquire(spec)
        scheduler.release("t3", keep_model=True)
        self.assertEqual([], scheduler.idle_model_leases(now=time.time() + 10 ** 6))
        self.assertTrue(scheduler.leases.holds("large_local_models", "t3"))


class HostMemoryTests(unittest.TestCase):
    def test_swap_report_is_bounded_when_available(self):
        # swap is reported, never tuned: swapping behaviour is the owner's host
        # configuration, and Boru only makes its own footprint smaller
        total, free = detect_swap()
        if total is None:
            self.skipTest("swap is not reported on this platform")
        self.assertGreaterEqual(total, 0)
        self.assertGreaterEqual(free, 0)
        self.assertLessEqual(free, total)

    def test_detected_memory_is_bounded_when_available(self):
        total, available = detect_memory()
        if total is None:
            self.skipTest("host memory is not reported on this platform")
        self.assertGreater(total, 0)
        self.assertGreaterEqual(available, 0)
        self.assertLessEqual(available, total)
        share = memory_pressure()
        if share is not None:
            self.assertTrue(0.0 <= share <= 1.0)


class ConfigWiringTests(unittest.TestCase):
    def providers(self):
        return (ProviderConfig(kind="mock"),)

    def test_default_profile_is_balanced(self):
        config = CoreConfig(providers=self.providers())
        self.assertEqual("BALANCED", config.resource_profile().mode.value)

    def test_bad_mode_and_overrides_are_configuration_errors(self):
        self.assertTrue(CoreConfig(providers=self.providers(), resource_mode="NOPE").validate())
        self.assertTrue(CoreConfig(providers=self.providers(), resource_mode="CUSTOM").validate())
        self.assertTrue(CoreConfig(providers=self.providers(),
                                   resource_overrides={"nope": 1}).validate())
        self.assertEqual([], CoreConfig(providers=self.providers(), resource_mode="PERFORMANCE").validate())


if __name__ == "__main__":
    unittest.main()
