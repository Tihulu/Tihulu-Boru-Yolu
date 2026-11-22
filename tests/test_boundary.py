"""Cross-boundary tracer tests: unclassified outbound requests are refused."""
import unittest

from boru.boundary import BOUNDARIES, DATA_CLASSES, RECIPIENTS, Classification, CrossBoundaryGuard
from boru.config import (
    MAX_CLASSIFICATIONS,
    MAX_PROVIDERS,
    ClassificationSpec,
    CoreConfig,
    ProviderConfig,
)
from boru.core import BoruCore
from boru.errors import PolicyViolation
from boru.types import TaskEnvelope


class GuardTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(("none", "L0", "L1", "L2"), DATA_CLASSES)
        self.assertEqual(("local", "cloud", "repository", "worker"), RECIPIENTS)
        self.assertIn("model_inference", BOUNDARIES)

    def test_bad_classifications_rejected(self):
        for bad in (dict(boundary="telepathy", recipient="local"),
                    dict(boundary="model_inference", recipient="someone"),
                    dict(boundary="model_inference", recipient="local", data_class="L7"),
                    dict(boundary="model_inference", recipient="local", data_class="L0"),
                    dict(boundary="model_inference", recipient="local", data_class="L2"),
                    dict(boundary="model_inference", recipient="local", data_class="L2", grant_ref="g")):
            self.assertTrue(Classification(**bad).validate(), bad)
        self.assertEqual([], Classification(boundary="model_inference", recipient="local").validate())
        self.assertEqual([], Classification(boundary="model_inference", recipient="cloud",
                                            data_class="L2", grant_ref="g").validate())

    def test_declare_is_single_use_per_direction(self):
        guard = CrossBoundaryGuard()
        guard.declare("t1", Classification(boundary="model_inference", recipient="local"))
        with self.assertRaises(PolicyViolation):
            guard.declare("t1", Classification(boundary="model_inference", recipient="local"))
        guard.declare("t2", Classification(boundary="model_inference", recipient="local"))
        guard.check("t1", recipient="local", boundary="model_inference")
        guard.check("t2", recipient="local", boundary="model_inference")
        # a data-carrying check above the declared class is denied and not counted
        self.assertEqual((False, "data_class_not_declared"),
                         guard.check("t2", recipient="local", boundary="model_inference",
                                     data_class="L0"))
        self.assertEqual(1, guard.uses("t1"))
        self.assertEqual(1, guard.uses("t2"))

    def test_unclassified_and_mismatched_requests_deny(self):
        guard = CrossBoundaryGuard()
        guard.declare("t1", Classification(boundary="model_inference", recipient="local"))
        self.assertEqual((True, ""), guard.check("t1", recipient="local", boundary="model_inference"))
        for kwargs in (dict(recipient="local", boundary="repository_api"),
                       dict(recipient="cloud", boundary="model_inference"),
                       dict(recipient="worker", boundary="model_inference")):
            allowed, reason = guard.check("t1", **kwargs)
            self.assertEqual((False, "unclassified_request"), (allowed, reason), kwargs)
        self.assertEqual((False, "unclassified_request"),
                         guard.check("t9", recipient="local", boundary="model_inference"))

    def test_data_class_and_grant_are_enforced(self):
        guard = CrossBoundaryGuard()
        guard.declare("t2", Classification(boundary="model_inference", recipient="cloud",
                                           data_class="L0", grant_ref="grant-1"))
        self.assertEqual((True, ""), guard.check("t2", recipient="cloud", boundary="model_inference",
                                                data_class="L0", grant_ref="grant-1"))
        self.assertEqual((False, "data_class_not_declared"),
                         guard.check("t2", recipient="cloud", boundary="model_inference",
                                     data_class="L1", grant_ref="grant-1"))
        self.assertEqual((False, "grant_mismatch"),
                         guard.check("t2", recipient="cloud", boundary="model_inference",
                                     data_class="L0", grant_ref="other"))
        self.assertEqual((False, "grant_mismatch"),
                         guard.check("t2", recipient="cloud", boundary="model_inference",
                                     data_class="L0"))

    def test_malformed_requests_deny(self):
        guard = CrossBoundaryGuard()
        guard.declare("t3", Classification(boundary="model_inference", recipient="local"))
        for task_id in ("", "x" * 200, 5):
            self.assertEqual((False, "malformed_request"),
                             guard.check(task_id, recipient="local", boundary="model_inference"))
        self.assertEqual((False, "unknown_data_class"),
                         guard.check("t3", recipient="local", boundary="model_inference",
                                     data_class="L7"))

    def test_bounded_identifier_api(self):
        guard = CrossBoundaryGuard()
        guard.declare("t4", Classification(boundary="model_inference", recipient="local"))
        self.assertEqual(["local/model_inference"], sorted(guard.declared_for("t4")))
        self.assertEqual(0, guard.uses("t4"))
        guard.check("t4", recipient="local", boundary="model_inference")
        self.assertEqual(1, guard.uses("t4"))
        with self.assertRaises(PolicyViolation):
            guard.uses("")


class ConfigAndCoreTests(unittest.TestCase):
    def test_spec_validation(self):
        for bad in (dict(boundary="telepathy", recipient="local"),
                    dict(boundary="model_inference", recipient="nobody"),
                    dict(boundary="model_inference", recipient="cloud", data_class="L2"),
                    dict(boundary="model_inference", recipient="local", data_class="L0"),
                    dict(boundary="model_inference", recipient="local", task_id="")):
            self.assertTrue(ClassificationSpec(**bad).validate(), bad)

    def test_config_roundtrip(self):
        config = CoreConfig.from_dict(CoreConfig.from_dict({
            "providers": [{"kind": "mock"}],
            "classifications": [{"boundary": "model_inference", "recipient": "local",
                                 "data_class": "none"}],
        }).to_dict())
        self.assertEqual(1, len(config.classifications))
        self.assertEqual("local", config.classifications[0].recipient)

    def test_bad_classification_config_rejected(self):
        for bad in ([{"boundary": "telepathy", "recipient": "local"}],
                    [{"boundary": "model_inference", "recipient": "cloud", "data_class": "L0"}],
                    [{"boundary": "model_inference", "recipient": "local", "task_id": ""}],
                    "nope"):
            with self.assertRaises(Exception):
                CoreConfig.from_dict({"providers": [{"kind": "mock"}], "classifications": bad})

    def test_in_process_provider_needs_no_declaration(self):
        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        self.assertEqual("REVIEW", engine.dispatch_next()["state"])
        engine.close()

    def test_outbound_provider_requires_a_declaration(self):
        engine = BoruCore(CoreConfig(providers=(ProviderConfig(
            kind="jan", endpoint="http://127.0.0.1:1337/v1", local_model_ids=("m",)),)))
        engine.submit(TaskEnvelope(task_id="t2", goal="ping"))
        summary = engine.dispatch_next()
        self.assertEqual(("HOLD", "unclassified_boundary"), (summary["state"], summary["reason"]))
        reasons = [row["reason"] for row in engine.audit.recent(8)]
        self.assertIn("unclassified_boundary", reasons)
        engine.close()

    def test_declared_local_direction_dispatches(self):
        engine = BoruCore(CoreConfig(providers=(ProviderConfig(
            kind="jan", endpoint="http://127.0.0.1:1337/v1", local_model_ids=("m",)),),
            classifications=(ClassificationSpec(boundary="model_inference", recipient="local"),)))
        engine.submit(TaskEnvelope(task_id="t3", goal="ping"))
        summary = engine.dispatch_next()
        self.assertNotEqual("unclassified_boundary", summary["reason"])
        self.assertIn(summary["state"], ("HOLD", "FAILED"))
        engine.close()

    def test_cloud_provider_requires_a_cloud_declaration(self):
        engine = BoruCore(CoreConfig(policy=__import__("boru.policy", fromlist=["Policy"]).Policy(
            inference_scope="CLOUD_ALLOWED", cloud_fallback_enabled=True),
            providers=(ProviderConfig(kind="cloud", endpoint="https://api.example.invalid/v1",
                                     api_key_env="BORU_TEST_KEY",
                                     local_model_ids=("m",)),)))
        engine.submit(TaskEnvelope(task_id="t4", goal="ping", inference_scope="CLOUD_ALLOWED"))
        summary = engine.dispatch_next()
        self.assertEqual(("HOLD", "unclassified_boundary"), (summary["state"], summary["reason"]))
        engine.close()


class ConfigurationBoundTests(unittest.TestCase):
    """A configuration is bounded work like every other input."""

    def jan_providers(self, count):
        return tuple(ProviderConfig(kind="jan", endpoint="http://127.0.0.1:1337/v1",
                                    local_model_ids=("m",))
                     for _ in range(count))

    def test_provider_count_is_bounded(self):
        self.assertEqual([], CoreConfig(providers=self.jan_providers(MAX_PROVIDERS)).validate())
        self.assertTrue(CoreConfig(providers=self.jan_providers(MAX_PROVIDERS + 1)).validate())

    def test_classification_count_is_bounded(self):
        specs = tuple(ClassificationSpec(boundary="model_inference", recipient="local")
                      for _ in range(MAX_CLASSIFICATIONS + 1))
        self.assertTrue(CoreConfig(providers=(ProviderConfig(kind="mock"),),
                                   classifications=specs).validate())


if __name__ == "__main__":
    unittest.main()
