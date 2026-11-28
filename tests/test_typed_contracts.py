"""Typed contract tests: unknown fields and private fields cannot pass."""
import unittest

from boru.errors import ContractError
from boru.policy import Policy
from boru.types import AgentResult, TaskEnvelope


class TaskEnvelopeTests(unittest.TestCase):
    def test_minimal_envelope_valid(self):
        envelope = TaskEnvelope(task_id="t1", goal="ping")
        self.assertEqual([], envelope.validate())
        self.assertEqual("LOCAL_ONLY", envelope.inference_scope)

    def test_unknown_and_missing_fields_rejected(self):
        with self.assertRaises(ContractError):
            TaskEnvelope.from_dict({"task_id": "t", "goal": "g", "extra": 1})
        with self.assertRaises(ContractError):
            TaskEnvelope.from_dict({"task_id": "t"})
        with self.assertRaises(ContractError):
            TaskEnvelope.from_dict(["not", "a", "mapping"])

    def test_bad_scalars_rejected(self):
        for bad in (
            {"max_attempts": True},
            {"max_parallel": 0},
            {"priority": "high"},
            {"token_budget": -1},
            {"token_budget": True},
            {"cost_budget_usd": float("nan")},
            {"capability_tags": "text"},
            {"capability_tags": ("ok", "")},
            {"schema_version": 99},
        ):
            envelope = TaskEnvelope(task_id="t", goal="g", **bad)
            self.assertTrue(envelope.validate(), bad)
        self.assertTrue(TaskEnvelope(task_id="t", goal="   ").validate())

    def test_private_payload_fields_rejected(self):
        for key in ("raw_stdout", "environment", "api_key", "directory_listing", "file_contents"):
            envelope = TaskEnvelope(task_id="t", goal="g", payload={key: "x"})
            self.assertTrue(envelope.validate(), key)

    def test_deadline_validation(self):
        self.assertEqual([], TaskEnvelope(task_id="t", goal="g", deadline="2030-01-01T00:00:00Z").validate())
        self.assertTrue(TaskEnvelope(task_id="t", goal="g", deadline="2030-01-01T00:00:00").validate())
        self.assertTrue(TaskEnvelope(task_id="t", goal="g", deadline="nope").validate())
        self.assertTrue(TaskEnvelope(task_id="t", goal="g", deadline="x" * 64).validate())

    def test_selected_model_pairing(self):
        self.assertTrue(TaskEnvelope(task_id="t", goal="g", selected_model="m").validate())
        self.assertEqual([], TaskEnvelope(task_id="t", goal="g", selected_provider="mock",
                                          selected_model="mock-text-v1").validate())

    def test_roundtrip_is_stable(self):
        envelope = TaskEnvelope(task_id="t", goal="g", capability_tags=("text",), deadline="2030-01-01T00:00:00Z")
        restored = TaskEnvelope.from_dict(envelope.to_dict())
        self.assertEqual(envelope.to_dict(), restored.to_dict())

    def test_manual_requires_selection_and_child_keeps_axes(self):
        parent = TaskEnvelope(task_id="p", goal="parent", routing_mode="MANUAL",
                              selected_provider="mock", selected_model="mock-text-v1",
                              inference_scope="LOCAL_ONLY")
        child = parent.child("c", "child")
        self.assertEqual(parent.inference_scope, child.inference_scope)
        self.assertEqual(parent.execution_profile, child.execution_profile)
        self.assertEqual(parent.disclosure_policy, child.disclosure_policy)
        self.assertEqual(parent.routing_mode, child.routing_mode)
        with self.assertRaises(ContractError):
            parent.child("c2", "child", inference_scope="CLOUD_ALLOWED")


class AgentResultTests(unittest.TestCase):
    def _result(self, **overrides):
        base = dict(task_id="t1", attempt_id="a1", status="completed", model_provider="mock",
                    model_id="mock-text-v1", evidence_class="simulated", typed_result={"text": "hi"},
                    usage_if_observed={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
        base.update(overrides)
        return AgentResult(**base)

    def test_completed_requires_provide_and_model(self):
        self.assertTrue(self._result(model_provider="").validate())
        self.assertTrue(self._result(model_model=None).validate() if False else self._result(model_id="").validate())

    def test_evidence_class_must_be_known(self):
        self.assertTrue(self._result(evidence_class="guessed").validate())

    def test_typed_result_rejects_private_fields(self):
        for key in ("raw_stdout", "environment", "token", "home_path"):
            self.assertTrue(self._result(typed_result={key: "x"}).validate(), key)

    def test_typed_result_size_bounds(self):
        self.assertTrue(self._result(typed_result={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}).validate(4))
        self.assertEqual([], self._result(typed_result={"a": 1, "b": 2}).validate(4))

    def test_usage_inconsistency_rejected(self):
        from boru.providers.base import ChatReply

        with self.assertRaises(ValueError):
            ChatReply(provider="mock", model_id="m", request_id="r", content="hi", evidence_class="simulated",
                      usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 5})
        with self.assertRaises(ValueError):
            ChatReply(provider="mock", model_id="m", request_id="r", content="hi", evidence_class="simulated",
                      usage={"prompt_tokens": 1})
        with self.assertRaises(ValueError):
            ChatReply(provider="mock", model_id="m", request_id="r", content="hi", evidence_class="live")

    def test_roundtrip_is_stable(self):
        result = self._result()
        self.assertEqual(result.to_dict(), AgentResult.from_dict(result.to_dict()).to_dict())
        with self.assertRaises(ContractError):
            AgentResult.from_dict({"task_id": "t", "attempt_id": "a", "status": "completed", "nope": 1})


class PolicyAlignmentTests(unittest.TestCase):
    def test_policy_and_contract_defaults_agree(self):
        policy = Policy()
        envelope = TaskEnvelope(task_id="t", goal="g")
        self.assertEqual(policy.inference_scope, envelope.inference_scope)
        self.assertEqual(policy.execution_profile, envelope.execution_profile)
        self.assertEqual(policy.disclosure_policy, envelope.disclosure_policy)


class EnvelopePayloadBoundTests(unittest.TestCase):
    """An envelope's payload is bounded like its result is."""

    def envelope(self, payload):
        return TaskEnvelope(task_id="t", goal="g", payload=payload)

    def test_hostile_payloads_are_refused(self):
        for label, payload in (
            ("huge content", {"messages": [{"role": "user", "content": "x" * 20_000_000}]}),
            ("too many messages", {"messages": [{"role": "user", "content": "x"}] * 100}),
            ("unknown payload key", {"messages": [], "extra": 1}),
            ("unknown role", {"messages": [{"role": "system2", "content": "x"}]}),
            ("extra message field", {"messages": [{"role": "user", "content": "x", "secret": 1}]}),
            ("private key", {"raw_stdout": "x"}),
            ("messages not a list", {"messages": {"role": "user"}}),
        ):
            errors = self.envelope(payload).validate()
            self.assertTrue(errors, label + " must not validate")

    def test_a_well_formed_payload_is_accepted(self):
        for payload in ({}, {"messages": [{"role": "user", "content": "ping"}]},
                       {"messages": [{"role": "system", "content": "rules"},
                                     {"role": "assistant", "content": "ack"}]}):
            self.assertEqual([], self.envelope(payload).validate(), payload)

    def test_core_submission_refuses_an_unbounded_payload(self):
        from boru.config import CoreConfig, ProviderConfig
        from boru.core import BoruCore
        from boru.errors import ContractError

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        try:
            with self.assertRaises(ContractError):
                engine.submit(self.envelope(
                    {"messages": [{"role": "user", "content": "x" * 20_000_000}]}))
            engine.submit(self.envelope({"messages": [{"role": "user", "content": "ping"}]}))
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
