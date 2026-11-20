"""Routing tests: modes change the choice, never the permissions."""
import unittest

from boru.errors import PolicyViolation
from boru.policy import Policy
from boru.registry import ModelRecord, ModelRegistry
from boru.router import Router, fallback_order, rank, should_retry


def registry() -> ModelRegistry:
    store = ModelRegistry()
    store.register(ModelRecord(provider="mock", model_id="small-text", tags=("text",), health="healthy",
                               local=True, cost_tier=0, quality_tier=1, max_context=8192, source="verified"))
    store.register(ModelRecord(provider="mock", model_id="large-text", tags=("text",), health="healthy",
                               local=True, cost_tier=3, quality_tier=9, max_context=200000, source="verified"))
    store.register(ModelRecord(provider="remote", model_id="cloud-text", tags=("text",), health="healthy",
                               local=False, cost_tier=5, quality_tier=9, max_context=200000, source="discovered"))
    return store


class RouterTests(unittest.TestCase):
    def test_local_only_never_lists_remote(self):
        router = Router(registry())
        for mode in ("AUTO", "ECONOMY", "BALANCED", "PERFORMANCE"):
            decision = router.decide(mode=mode, inference_scope="LOCAL_ONLY")
            self.assertTrue(all(candidate.local for candidate in decision.ordered), mode)
            self.assertNotIn(("remote", "cloud-text"), [c.key for c in decision.ordered])

    def test_local_only_returns_empty_when_only_remote_exists(self):
        store = ModelRegistry()
        store.register(ModelRecord(provider="remote", model_id="only-cloud", tags=("text",),
                                   health="healthy", local=False))
        decision = Router(store).decide(mode="PERFORMANCE", inference_scope="LOCAL_ONLY")
        self.assertIsNone(decision.selected)
        self.assertEqual((), decision.ordered)

    def test_modes_select_different_candidates(self):
        router = Router(registry())
        economy = router.decide(mode="ECONOMY", inference_scope="LOCAL_ONLY")
        performance = router.decide(mode="PERFORMANCE", inference_scope="LOCAL_ONLY")
        self.assertEqual("small-text", economy.selected.model_id)
        self.assertEqual("large-text", performance.selected.model_id)

    def test_auto_follows_complexity_without_widening_policy(self):
        router = Router(registry())
        policy = Policy()
        simple = router.decide(mode="AUTO", inference_scope="LOCAL_ONLY", complexity="simple")
        difficult = router.decide(mode="AUTO", inference_scope="LOCAL_ONLY", complexity="difficult")
        self.assertEqual("small-text", simple.selected.model_id)
        self.assertEqual("large-text", difficult.selected.model_id)
        self.assertEqual(policy.inference_scope, "LOCAL_ONLY")

    def test_manual_requires_and_uses_owner_selection(self):
        router = Router(registry())
        with self.assertRaises(PolicyViolation):
            router.decide(mode="MANUAL", inference_scope="LOCAL_ONLY")
        decision = router.decide(mode="MANUAL", inference_scope="LOCAL_ONLY",
                                selected_provider="mock", selected_model="large-text")
        self.assertEqual(("mock", "large-text"), decision.selected.key)
        self.assertEqual(("owner_selected",), decision.selected.reasons)
        with self.assertRaises(PolicyViolation):
            router.decide(mode="MANUAL", inference_scope="LOCAL_ONLY",
                          selected_provider="remote", selected_model="cloud-text")

    def test_context_requirement_excludes_small_models(self):
        router = Router(registry())
        decision = router.decide(mode="PERFORMANCE", inference_scope="LOCAL_ONLY", required_context=50000)
        self.assertEqual("large-text", decision.selected.model_id)
        tiny = Router(ModelRegistry()).decide(mode="AUTO", inference_scope="LOCAL_ONLY")
        self.assertIsNone(tiny.selected)

    def test_capability_tags_filter(self):
        store = ModelRegistry()
        store.register(ModelRecord(provider="mock", model_id="text-only", tags=("text",), health="healthy",
                                   local=True, source="verified"))
        store.register(ModelRecord(provider="mock", model_id="text-code", tags=("text", "code"), health="healthy",
                                   local=True, source="verified"))
        router = Router(store)
        decision = router.decide(mode="BALANCED", inference_scope="LOCAL_ONLY", required_tags=("text", "code"))
        self.assertEqual("text-code", decision.selected.model_id)

    def test_unhealthy_models_excluded(self):
        store = ModelRegistry()
        store.register(ModelRecord(provider="mock", model_id="down", health="down", tags=("text",), local=True))
        store.register(ModelRecord(provider="mock", model_id="ok", health="healthy", tags=("text",), local=True))
        decision = Router(store).decide(mode="AUTO", inference_scope="LOCAL_ONLY")
        self.assertEqual("ok", decision.selected.model_id)

    def test_unknown_mode_and_scope_rejected(self):
        router = Router(registry())
        with self.assertRaises(PolicyViolation):
            router.decide(mode="TURBO", inference_scope="LOCAL_ONLY")
        with self.assertRaises(PolicyViolation):
            router.decide(mode="AUTO", inference_scope="WHENEVER")

    def test_unknown_credits_are_never_invented(self):
        record = registry().get("remote", "cloud-text")
        self.assertEqual("UNKNOWN", record.credits)  # no assumed quota
        plain = ModelRecord(provider="mock", model_id="m", tags=("text",), health="healthy", local=True)
        self.assertIsNone(plain.cost_tier)
        self.assertIsNone(plain.quality_tier)
        self.assertIsNone(plain.max_context)

    def test_bad_metadata_rejected(self):
        from boru.errors import ContractError

        for bad in (dict(cost_tier=99), dict(quality_tier=True), dict(max_context=0), dict(tags=("text", "ok", ""))):
            with self.assertRaises(ContractError):
                ModelRecord(provider="mock", model_id="m", **bad)

    def test_fallback_order_preserves_policy(self):
        decision = Router(registry()).decide(mode="PERFORMANCE", inference_scope="CLOUD_ALLOWED")
        remaining = fallback_order(decision, failed=decision.ordered[0].key)
        self.assertTrue(all(candidate.key != decision.ordered[0].key for candidate in remaining))
        self.assertTrue(all(candidate in decision.ordered for candidate in remaining))
        self.assertTrue(all(candidate.local or decision.mode != "LOCAL_ONLY" for candidate in decision.ordered))

    def test_retryable_and_terminal_categories(self):
        for category in ("timeout", "unavailable", "rate_limited", "server_error"):
            self.assertTrue(should_retry(category), category)
        for category in ("policy_denied", "invalid_response", "request_too_large", "unauthorized"):
            self.assertFalse(should_retry(category), category)

    def test_rank_rejects_mode(self):
        with self.assertRaises(PolicyViolation):
            rank("FAST", [], local_only=True)


class FallbackIsolationTests(unittest.TestCase):
    """Fallback may select another candidate but never another permission."""

    def test_fallback_cannot_widen_scope(self):
        router = Router(registry())
        decision = router.decide(mode="AUTO", inference_scope="LOCAL_ONLY")
        remaining = fallback_order(decision, failed=decision.ordered[0].key)
        self.assertTrue(all(candidate.local for candidate in remaining))


if __name__ == "__main__":
    unittest.main()
