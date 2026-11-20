"""Core orchestration tests: axes, dispatch, verification and cancellation."""
import unittest

from boru.config import CoreConfig, ProviderConfig
from boru.core import BoruCore
from boru.errors import PolicyViolation, StoreError
from boru.policy import Policy
from boru.registry import ModelRecord, ModelRegistry
from boru.store import TaskStore
from boru.types import TaskEnvelope

STAMP = "2026-01-01T00:00:00Z"


class RecordingProvider(unittest.TestCase):
    """Provider double that records every attempted call."""

    def setUp(self):
        self.calls = []

    def provider_double(self):
        calls = self.calls

        class Doubled:
            provider = "mock"
            local = True

            def discover(self):
                return ("mock-text-v1",)

            def chat(self, model_id, messages, *, max_tokens=128, timeout=30.0):
                from boru.providers.base import ChatReply

                calls.append({"model_id": model_id, "messages": len(messages), "timeout": timeout})
                return ChatReply(provider="mock", model_id=model_id, request_id="req-{}".format(len(calls)),
                                 content="ack", evidence_class="simulated")

        return Doubled()


def core(providers=None, policy=None, store=None):
    config = CoreConfig(providers=providers or (ProviderConfig(kind="mock"),), policy=policy or Policy())
    return BoruCore(config, store=store)


class DispatchTests(RecordingProvider):
    def test_full_pipeline_with_mock(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        summary = engine.dispatch_next()
        self.assertEqual("REVIEW", summary["state"])
        self.assertEqual("mock", summary["provider"])
        self.assertEqual("mock-text-v1", summary["model_id"])
        self.assertEqual("simulated", summary["evidence_class"])
        self.assertEqual("HOLD", summary["live_acceptance"])
        self.assertEqual("DONE", engine.review("t1", accept=True))
        engine.close()

    def test_payload_messages_are_used(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="ping",
                                   payload={"messages": [{"role": "user", "content": "hello"}]}))
        engine.dispatch_next()
        engine.close()

    def test_review_cannot_be_repeated(self):
        from boru.errors import VerificationError

        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        engine.dispatch_next()
        engine.review("t1", accept=True)
        with self.assertRaises(VerificationError):
            engine.review("t1", accept=True)
        engine.close()

    def test_rejection_records_failure(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        engine.dispatch_next()
        self.assertEqual("FAILED", engine.review("t1", accept=False))
        engine.close()

    def test_dispatch_with_empty_queue(self):
        engine = core()
        self.assertIsNone(engine.dispatch_next())
        engine.close()

    def test_policy_mismatch_rejected_before_dispatch(self):
        engine = core()
        for bad in (TaskEnvelope(task_id="t1", goal="g", inference_scope="CLOUD_ALLOWED"),
                    TaskEnvelope(task_id="t2", goal="g", execution_profile="HYBRID_PRIVATE"),
                    TaskEnvelope(task_id="t3", goal="g", disclosure_policy="SCOPED_APPROVED"),
                    TaskEnvelope(task_id="t4", goal="g", routing_mode="ECONOMY")):
            with self.assertRaises(PolicyViolation):
                engine.submit(bad)
        self.assertEqual([], engine.store.queued())
        engine.close()

    def test_manual_mode_requires_selection(self):
        policy = Policy(optimization_mode="MANUAL")
        engine = core(policy=policy)
        with self.assertRaises(PolicyViolation):
            engine.submit(TaskEnvelope(task_id="t1", goal="g", routing_mode="MANUAL"))
        engine.close()

    def test_manual_mode_uses_selected_model(self):
        policy = Policy(optimization_mode="MANUAL")
        engine = core(policy=policy, providers=(ProviderConfig(kind="mock"),))
        engine.submit(TaskEnvelope(task_id="t1", goal="g", routing_mode="MANUAL",
                                   selected_provider="mock", selected_model="mock-text-v1"))
        summary = engine.dispatch_next()
        self.assertEqual("REVIEW", summary["state"])
        self.assertEqual("mock-text-v1", summary["model_id"])
        engine.close()

    def test_manual_unknown_provider_rejected(self):
        policy = Policy(optimization_mode="MANUAL")
        engine = core(policy=policy)
        with self.assertRaises(PolicyViolation):
            engine.submit(TaskEnvelope(task_id="t1", goal="g", routing_mode="MANUAL",
                                       selected_provider="nowhere", selected_model="x"))
        engine.close()

    def test_capability_restricted_to_text(self):
        engine = core()
        for tags in (("shell",), ("browser",), ("code",)):
            with self.assertRaises(PolicyViolation):
                engine.submit(TaskEnvelope(task_id="t1", goal="g", capability_tags=tags))

    def test_deadline_hold_makes_no_call(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", deadline="2000-01-01T00:00:00Z"))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("deadline_exceeded", summary["reason"])
        engine.close()

    def test_ceiling_over_estimate_holds_without_a_call(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", token_budget=100))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("budget_exceeded_pre_dispatch", summary["reason"])
        engine.close()

    def test_generous_ceiling_dispatches_and_records_usage(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", token_budget=100000))
        summary = engine.dispatch_next()
        self.assertEqual("REVIEW", summary["state"])
        self.assertEqual({"input_tokens": 8, "output_tokens": 8, "total_tokens": 16},
                         summary["usage_if_observed"])
        observed = engine.budgets.observed("t1")
        self.assertEqual(4, observed["estimated_input"])  # labelled estimate
        self.assertEqual(16, observed["observed_total"])  # labelled observation
        engine.close()

    def test_cost_ceiling_refuses_an_unbounded_spend(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", cost_budget_usd=0.0001))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("cost_ceiling_unresolvable_before_dispatch", summary["reason"])
        engine.close()

    def test_reported_usage_over_ceiling_holds_after_the_call(self):
        from boru.config import CoreConfig, ProviderConfig
        from boru.providers.base import ChatReply

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),), max_output_tokens=8))
        engine.submit(TaskEnvelope(task_id="t1", goal="g", token_budget=30))
        original = engine._providers["mock"].chat

        def overstated(model_id, messages, **kwargs):
            reply = original(model_id, messages, **kwargs)
            return ChatReply(provider="mock", model_id=model_id, request_id=reply.request_id,
                             content=reply.content, evidence_class="simulated",
                             usage={"input_tokens": 20, "output_tokens": 20, "total_tokens": 40})

        engine._providers["mock"].chat = overstated
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("budget_exceeded_after_reported_usage", summary["reason"])
        engine.close()

    def test_cancel_prevents_dispatch(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        self.assertEqual("CANCELLED", engine.cancel("t1"))
        self.assertIsNone(engine.dispatch_next())
        self.assertEqual("CANCELLED", engine.status("t1")["state"])
        engine.close()

    def test_cancel_unknown_task_rejected(self):
        engine = core()
        with self.assertRaises(StoreError):
            engine.cancel("nope")
        engine.close()

    def test_configuration_without_any_provider_is_refused(self):
        from boru.errors import ConfigurationError

        with self.assertRaises(ConfigurationError):
            CoreConfig.from_dict({"providers": []})
        with self.assertRaises(ConfigurationError):
            CoreConfig.from_dict({})

    def test_provider_without_a_model_holds_without_call(self):
        from boru.registry import ModelRegistry

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        engine.router.registry = ModelRegistry()  # no permitted candidates
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("missing_provider", summary["reason"])
        engine.close()

    def test_failed_reply_is_not_done(self):
        from boru.providers.base import ProviderFailure

        class Broken:
            provider = "mock"
            local = True

            def discover(self):
                return ("mock-text-v1",)

            def chat(self, model_id, messages, *, max_tokens=128, timeout=30.0):
                raise ProviderFailure("timeout", "provider timed out")

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        engine._providers = {"mock": Broken()}
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("provider_unavailable", summary["reason"])
        engine.close()

    def test_forged_reply_never_becomes_done(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))

        class Forged:
            provider = "mock"
            local = True

            def discover(self):
                return ("mock-text-v1",)

            def chat(self, model_id, messages, *, max_tokens=128, timeout=30.0):
                from boru.providers.base import ChatReply

                return ChatReply(provider="elsewhere", model_id="elsewhere", request_id="forged",
                                 content="ack", evidence_class="direct")

        engine._providers = {"mock": Forged()}
        summary = engine.dispatch_next()
        self.assertEqual("FAILED", summary["state"])
        self.assertEqual("verification_failed", summary["reason"])
        engine.close()

    def test_policy_object_is_immutable_inside_core(self):
        engine = core()
        before = engine.policy.as_dict()
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        engine.dispatch_next()
        engine.review("t1", accept=True)
        self.assertEqual(before, engine.policy.as_dict())
        engine.close()


class StateStoreIntegrationTests(RecordingProvider):
    def test_interrupted_task_holds_after_restart(self):
        import tempfile, os, shutil

        root = tempfile.mkdtemp(prefix="boru-core-")
        os.chmod(root, 0o700)
        try:
            store = TaskStore(root)
            engine = core(store=store)
            engine.submit(TaskEnvelope(task_id="t1", goal="g"))
            store.transition("t1", "QUEUED", "RUNNING", "dispatch_started", STAMP)
            engine.close()
            reopened = core(store=TaskStore(root))
            self.assertEqual(["t1"], reopened.recover())
            self.assertEqual("HOLD", reopened.status("t1")["state"])
            reopened.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_queued_task_restores_after_restart(self):
        import tempfile, os, shutil

        root = tempfile.mkdtemp(prefix="boru-core-")
        os.chmod(root, 0o700)
        try:
            store = TaskStore(root)
            engine = core(store=store)
            engine.submit(TaskEnvelope(task_id="t1", goal="g"))
            store.transition("t1", "QUEUED", "HOLD", "paused", STAMP)
            engine.close()
            reopened = core(store=TaskStore(root))
            reopened.store.transition("t1", "HOLD", "QUEUED", "resumed", STAMP)
            summary = reopened.dispatch_next()
            self.assertEqual("REVIEW", summary["state"])
            self.assertEqual("t1", summary["task_id"])
            reopened.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class FallbackIntegrationTests(unittest.TestCase):
    """Bounded fallback changes the candidate, never the permission."""

    def engine_with(self, models, script, *, policy=None, max_retries=None):
        from boru.registry import ModelRecord

        policy = policy or Policy(max_retries=max_retries if max_retries is not None else 2)
        config = CoreConfig(providers=(ProviderConfig(kind="mock"),), policy=policy)
        engine = BoruCore(config)
        registry = ModelRegistry()
        for model_id in models:
            registry.register(ModelRecord(provider="mock", model_id=model_id, tags=("text",), health="healthy",
                                          local=True, source="verified"))
        engine.router.registry = registry
        calls: list = []
        engine._providers = {"mock": _ScriptedProvider(script, calls)}
        return engine, calls

    def test_retryable_failure_moves_to_next_local_candidate(self):
        from boru.providers.base import ChatReply, ProviderFailure

        def script(model_id):
            if model_id == "first":
                raise ProviderFailure("rate_limited", "provider rate limit reached")
            return ChatReply(provider="mock", model_id=model_id, request_id="req-second", content="ok",
                             evidence_class="simulated")

        engine, calls = self.engine_with(["first", "second"], script, max_retries=1)
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = engine.dispatch_next()
        self.assertEqual(["first", "second"], calls)
        self.assertEqual("REVIEW", summary["state"])
        self.assertEqual("second", summary["model_id"])
        self.assertEqual("simulated", summary["evidence_class"])
        engine.close()

    def test_terminal_failure_does_not_retry(self):
        from boru.providers.base import ProviderFailure

        def script(model_id):
            raise ProviderFailure("invalid_response", "provider returned malformed output")

        engine, calls = self.engine_with(["first", "second", "third"], script, max_retries=3)
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = engine.dispatch_next()
        self.assertEqual(["first"], calls)
        self.assertEqual("FAILED", summary["state"])
        self.assertEqual("invalid_reply", summary["reason"])
        engine.close()

    def test_fallback_stays_local_under_local_only(self):
        from boru.providers.base import ProviderFailure

        def script(model_id):
            raise ProviderFailure("timeout", "provider timed out")

        engine, calls = self.engine_with(["only-local"], script, max_retries=5)
        engine.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = engine.dispatch_next()
        self.assertEqual(["only-local"], calls)
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("provider_unavailable", summary["reason"])
        engine.close()

    def test_fallback_keeps_policy_unchanged(self):
        from boru.providers.base import ChatReply, ProviderFailure
        from boru.registry import ModelRecord

        def script(model_id):
            if model_id == "beta":
                raise ProviderFailure("server_error", "provider server error")
            return ChatReply(provider="mock", model_id=model_id, request_id="req-alpha", content="ok",
                             evidence_class="simulated")

        config = CoreConfig(providers=(ProviderConfig(kind="mock"),), policy=Policy(optimization_mode="PERFORMANCE"))
        engine = BoruCore(config)
        registry = ModelRegistry()
        registry.register(ModelRecord(provider="mock", model_id="beta", tags=("text",), health="healthy",
                                      local=True, source="verified", quality_tier=9))
        registry.register(ModelRecord(provider="mock", model_id="alpha", tags=("text",), health="healthy",
                                      local=True, source="verified", quality_tier=1))
        engine.router.registry = registry
        engine._providers = {"mock": _ScriptedProvider(script, calls=[])}
        before = engine.policy.as_dict()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", routing_mode="PERFORMANCE"))
        engine.dispatch_next()
        self.assertEqual(before, engine.policy.as_dict())
        engine.close()


def _ScriptedProvider(script, calls):
    """Provider double that replays a script and records attempted models."""

    class Scripted:
        provider = "mock"
        local = True

        def discover(self):
            return ("first", "second", "third", "beta", "alpha")

        def chat(self, model_id, messages, *, max_tokens=128, timeout=30.0):
            calls.append(model_id)
            return script(model_id)

    return Scripted()
