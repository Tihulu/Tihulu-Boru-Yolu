"""Policy axis tests: optimization never widens the other three domains."""
import unittest

from boru.errors import ContractError
from boru.policy import (
    CLOUD_SHELL_PROFILES,
    EXECUTION_PROFILES,
    INFERENCE_SCOPES,
    OPTIMIZATION_MODES,
    Policy,
)


class PolicyTests(unittest.TestCase):
    def test_safe_defaults_are_local(self):
        policy = Policy()
        self.assertEqual("LOCAL_ONLY", policy.inference_scope)
        self.assertEqual("LOCAL_ISOLATED", policy.execution_profile)
        self.assertEqual("MINIMUM_NECESSARY", policy.disclosure_policy)
        self.assertFalse(policy.cloud_fallback_enabled)
        self.assertEqual([], policy.validate())

    def test_invalid_policy_rejected_at_construction(self):
        with self.assertRaises(ContractError):
            Policy(max_agents=7)
        with self.assertRaises(ContractError):
            Policy(max_agents=True)
        with self.assertRaises(ContractError):
            Policy(optimization_mode="FAST")
        with self.assertRaises(ContractError):
            Policy(inference_scope="MAYBE")
        with self.assertRaises(ContractError):
            Policy(execution_profile="HOST_SHELL")
        with self.assertRaises(ContractError):
            Policy(disclosure_policy="ANYTHING")
        with self.assertRaises(ContractError):
            Policy(cloud_shell_enabled=1)
        with self.assertRaises(ContractError):
            Policy(cloud_fallback_enabled="yes")
        with self.assertRaises(ContractError):
            Policy(max_result_fields=0)
        with self.assertRaises(ContractError):
            Policy(max_retries=True)

    def test_optimization_change_never_touches_other_axes(self):
        base = Policy()
        for mode in OPTIMIZATION_MODES:
            changed = base.with_optimization(mode)
            self.assertEqual(mode, changed.optimization_mode)
            self.assertEqual(base.inference_scope, changed.inference_scope)
            self.assertEqual(base.execution_profile, changed.execution_profile)
            self.assertEqual(base.disclosure_policy, changed.disclosure_policy)
            self.assertEqual(base.as_dict()["inference_scope"], changed.as_dict()["inference_scope"])

    def test_with_optimization_rejects_unknown_mode(self):
        with self.assertRaises(ContractError):
            Policy().with_optimization("TURBO")

    def test_local_only_forbids_cloud_fallback(self):
        with self.assertRaises(ContractError):
            Policy(inference_scope="LOCAL_ONLY", cloud_fallback_enabled=True)
        self.assertEqual([], Policy(inference_scope="LOCAL_ONLY").validate())

    def test_cloud_shell_requires_consent_and_sandbox(self):
        for profile in sorted(CLOUD_SHELL_PROFILES):
            with self.assertRaises(ContractError):
                Policy(execution_profile=profile, inference_scope="CLOUD_ALLOWED")
            with self.assertRaises(ContractError):
                Policy(execution_profile=profile, inference_scope="CLOUD_ALLOWED",
                       cloud_shell_enabled=True, cloud_shell_live_consent_required=False)
            with self.assertRaises(ContractError):
                Policy(execution_profile=profile, inference_scope="CLOUD_ALLOWED",
                       cloud_shell_enabled=True, cloud_shell_sandbox_required=False)
            valid = Policy(execution_profile=profile, inference_scope="CLOUD_ALLOWED", cloud_shell_enabled=True)
            self.assertTrue(valid.allows_cloud_shell())

    def test_cloud_shell_incompatible_with_local_only(self):
        with self.assertRaises(ContractError):
            Policy(inference_scope="LOCAL_ONLY", execution_profile="CLOUD_SHELL_APPROVAL", cloud_shell_enabled=True)

    def test_raw_output_flags_are_rejected(self):
        with self.assertRaises(ContractError):
            Policy(raw_tool_output_to_cloud=True)
        with self.assertRaises(ContractError):
            Policy(recipient_bound_consent_required=False)

    def test_all_mode_constants_present(self):
        self.assertEqual({"AUTO", "ECONOMY", "BALANCED", "PERFORMANCE", "MANUAL"}, set(OPTIMIZATION_MODES))
        self.assertEqual({"LOCAL_ONLY", "CLOUD_ALLOWED"}, set(INFERENCE_SCOPES))
        self.assertEqual(4, len(EXECUTION_PROFILES))


if __name__ == "__main__":
    unittest.main()
