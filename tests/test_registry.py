"""Registry tests: locality, capability and selection are explicit."""
import unittest

from boru.errors import ContractError, PolicyViolation
from boru.registry import ModelRecord, ModelRegistry
from boru.policy import Policy


class RegistryTests(unittest.TestCase):
    def build(self) -> ModelRegistry:
        registry = ModelRegistry()
        registry.register(ModelRecord(provider="mock", model_id="mock-text-v1", source="verified",
                                      health="healthy", tags=("text",), local=True))
        registry.register(ModelRecord(provider="remote", model_id="cloud-model", source="discovered",
                                      health="healthy", tags=("text",), local=False))
        return registry

    def test_locality_is_never_inferred_from_name(self):
        # A record defaults to non-local: locality must be declared, never guessed.
        record = ModelRecord(provider="remote", model_id="m")
        self.assertFalse(record.local)
        registry = ModelRegistry()
        registry.register(record)
        self.assertEqual([], registry.candidates(local_only=True))
        self.assertEqual(["remote/m"], ["{}/{}".format(r.provider, r.model_id) for r in registry.candidates()])
        # An explicit local declaration is metadata the owner supplies.
        local_record = ModelRecord(provider="remote", model_id="m2", local=True)
        registry.register(local_record)
        self.assertIn(local_record, registry.candidates(local_only=True))

    def test_local_only_selects_no_remote_models(self):
        registry = self.build()
        local = registry.select("ECONOMY", "LOCAL_ONLY")
        self.assertEqual(["mock/mock-text-v1"], ["{}/{}".format(r.provider, r.model_id) for r in local])

    def test_cloud_allowed_lists_remote(self):
        registry = self.build()
        cloud = registry.select("PERFORMANCE", "CLOUD_ALLOWED")
        self.assertIn("remote/cloud-model", ["{}/{}".format(r.provider, r.model_id) for r in cloud])

    def test_tag_filtering_requires_all_tags(self):
        registry = ModelRegistry()
        registry.register(ModelRecord(provider="mock", model_id="m1", tags=("text",), health="healthy", local=True))
        registry.register(ModelRecord(provider="mock", model_id="m2", tags=("text", "code"), health="healthy", local=True))
        self.assertEqual(["m2"], [r.model_id for r in registry.candidates(tags=("text", "code"))])

    def test_discovery_is_not_verification(self):
        registry = ModelRegistry()
        added = registry.upsert_from_discovery("mock", ("fresh-model",))
        self.assertEqual("discovered", added[0].source)
        self.assertEqual("healthy", added[0].health)
        verified = ModelRecord(provider="mock", model_id="mock-text-v1", source="verified", health="healthy", local=True)
        registry.register(verified)
        rediscovered = registry.upsert_from_discovery("mock", ("mock-text-v1",))
        self.assertEqual("verified", rediscovered[0].source, "discovery must not silently demote a verified entry")

    def test_health_and_verification_updates(self):
        registry = self.build()
        registry.mark_health("mock", "mock-text-v1", "down", "timeout")
        self.assertEqual("down", registry.get("mock", "mock-text-v1").health)
        self.assertNotIn("mock/mock-text-v1", ["{}/{}".format(r.provider, r.model_id) for r in registry.candidates()])
        registry.mark_tested("mock", "mock-text-v1", "2026-01-01T00:00:00Z")
        self.assertEqual("verified", registry.get("mock", "mock-text-v1").source)

    def test_select_rejects_unknown_scope(self):
        with self.assertRaises(PolicyViolation):
            self.build().select("AUTO", "WHATEVER")

    def test_record_validation(self):
        for bad in (dict(provider="", model_id="m"), dict(provider="p", model_id=""),
                    dict(provider="p", model_id="m", source="invented"),
                    dict(provider="p", model_id="m", health="fine")):
            with self.assertRaises(ContractError):
                self.build().register(ModelRecord(**bad))


class MetadataPreservationTests(unittest.TestCase):
    """A health change must not erase owner-declared ranking metadata."""

    def record(self, **overrides):
        base = dict(provider="jan", model_id="m", source="configured", local=True,
                    cost_tier=3, quality_tier=4, tags=("text",))
        base.update(overrides)
        return ModelRecord(**base)

    def test_mark_health_preserves_tiers(self):
        registry = ModelRegistry()
        registry.register(self.record())
        registry.mark_health("jan", "m", "degraded", "rate_limited")
        stored = registry.get("jan", "m")
        self.assertEqual("degraded", stored.health)
        self.assertEqual("rate_limited", stored.last_error_kind)
        self.assertEqual(3, stored.cost_tier)
        self.assertEqual(4, stored.quality_tier)

    def test_mark_tested_promotes_and_keeps_tiers(self):
        registry = ModelRegistry()
        registry.register(self.record())
        registry.mark_tested("jan", "m", "2026-11-22T00:00:00Z")
        stored = registry.get("jan", "m")
        self.assertEqual("verified", stored.source)
        self.assertEqual("healthy", stored.health)
        self.assertEqual((3, 4), (stored.cost_tier, stored.quality_tier))

    def test_unknown_records_fail_typed(self):
        from boru.errors import ContractError

        registry = ModelRegistry()
        with self.assertRaises(ContractError):
            registry.mark_health("jan", "absent", "healthy")
        with self.assertRaises(ContractError):
            registry.mark_tested("jan", "absent", "2026-11-22T00:00:00Z")
        registry.register(self.record())
        with self.assertRaises(ContractError):
            registry.mark_health("jan", "m", "sideways")
        with self.assertRaises(ContractError):
            registry.mark_health("jan", "m", "healthy", "x" * 200)


if __name__ == "__main__":
    unittest.main()
