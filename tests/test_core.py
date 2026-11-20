"""Core orchestration tests: axes, dispatch, verification and cancellation."""
import unittest

from boru.config import CoreConfig, ProviderConfig
from boru.core import BoruCore
from boru.errors import PolicyViolation, StoreError
from boru.policy import Policy
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

    def test_budget_hold_makes_no_call(self):
        engine = core()
        engine.submit(TaskEnvelope(task_id="t1", goal="g", token_budget=100))
        summary = engine.dispatch_next()
        self.assertEqual("HOLD", summary["state"])
        self.assertEqual("budget_unverifiable", summary["reason"])
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
        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))

        class Empty:
            provider = "mock"
            local = True

            def discover(self):
                return ()

            def chat(self, *args, **kwargs):  # pragma: no cover - must never run
                raise AssertionError("no model means no dispatch")

        engine._providers = {"mock": Empty()}
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
