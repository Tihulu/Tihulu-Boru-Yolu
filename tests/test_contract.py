"""Source-only validation tests; no network, no services, no Shell."""
import copy
import json
import unittest
from pathlib import Path
from scripts.check_project import validate_example

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "examples/boru-yolu.example.json").read_text(encoding="utf-8"))


class ExampleContractTests(unittest.TestCase):
    def variant(self, **changes):
        obj = copy.deepcopy(BASE)
        for path, value in changes.items():
            parts = path.split("__")
            at = obj
            for key in parts[:-1]:
                at = at[key]
            at[parts[-1]] = value
        return obj

    def test_boru_core_independent_of_tihulu_auto(self):
        self.assertEqual("boru_core", BASE["orchestrator"]["engine"])
        self.assertFalse(BASE["orchestrator"]["tihulu_auto_required"])
        self.assertFalse(BASE["services"]["tihulu_auto"]["enabled"])
        self.assertEqual([], validate_example(BASE))

    def test_legacy_adapter_not_mandatory(self):
        bad = self.variant(orchestrator__tihulu_auto_required=True)
        self.assertIn("TIHULU-AUTO must never be required", validate_example(bad))
        bad2 = self.variant(services__tihulu_auto__required=True)
        self.assertIn("legacy adapter must not be required", validate_example(bad2))

    def test_standalone_opencode_and_jan(self):
        for flag in ("standalone_opencode", "standalone_jan"):
            bad = self.variant(**{"orchestrator__" + flag: False})
            self.assertIn("OpenCode and Jan must remain standalone", validate_example(bad))

    def test_mode_switch_does_not_change_permissions(self):
        base = BASE
        for mode in ("AUTO", "ECONOMY", "BALANCED", "PERFORMANCE", "MANUAL"):
            changed = self.variant(routing__optimization_mode=mode)
            self.assertEqual(base["execution"], changed["execution"])
            self.assertEqual(base["privacy"], changed["privacy"])
            self.assertEqual(base["routing"]["inference_scope"], changed["routing"]["inference_scope"])
            self.assertEqual([], validate_example(changed))

    def test_privacy_policy_scoped_approved_does_not_enable_raw_stdout(self):
        allowed = self.variant(privacy__policy="SCOPED_APPROVED")
        self.assertEqual([], validate_example(allowed))
        self.assertFalse(allowed["privacy"]["raw_tool_output_to_cloud"])
        bad = self.variant(privacy__policy="SCOPED_APPROVED", privacy__raw_tool_output_to_cloud=True)
        self.assertIn("raw_tool_output_to_cloud cannot be globally enabled", validate_example(bad))

    def test_unknown_privacy_policy_rejected(self):
        bad = self.variant(privacy__policy="UNRESTRICTED")
        self.assertIn("unknown privacy policy", validate_example(bad))

    def test_unbounded_result_fields_rejected(self):
        for value in (0, -1, True):
            bad = self.variant(privacy__max_result_fields=value)
            self.assertIn("max_result_fields must be a positive integer", validate_example(bad))

    def test_local_only_economy_and_performance_forbid_cloud_fallback(self):
        for mode in ("ECONOMY", "PERFORMANCE"):
            bad = self.variant(routing__optimization_mode=mode,
                               routing__inference_scope="LOCAL_ONLY")
            self.assertIn("LOCAL_ONLY forbids cloud fallback", validate_example(bad))
            good = self.variant(routing__optimization_mode=mode,
                                routing__inference_scope="LOCAL_ONLY",
                                routing__cloud_fallback_enabled=False)
            self.assertEqual([], validate_example(good))
            self.assertEqual("LOCAL_ISOLATED", good["execution"]["profile"])

    def test_safe_default_example(self):
        self.assertEqual([], validate_example(BASE))
        self.assertFalse(BASE["execution"]["cloud_shell"]["enabled"])

    def test_modes_do_not_change_default_shell(self):
        for mode in ("AUTO", "ECONOMY", "BALANCED", "PERFORMANCE", "MANUAL"):
            self.assertEqual([], validate_example(self.variant(routing__optimization_mode=mode)))

    def test_cloud_shell_never_silently_enables(self):
        bad = self.variant(execution__cloud_shell__enabled=True)
        self.assertIn("cloud_shell cannot be enabled in local-only Shell profile", validate_example(bad))

    def test_cloud_shell_approval_profile_explicit(self):
        good = self.variant(execution__profile="CLOUD_SHELL_APPROVAL", execution__cloud_shell__enabled=True)
        self.assertEqual([], validate_example(good))

    def test_cloud_shell_requires_sandbox(self):
        bad = self.variant(execution__profile="CLOUD_SHELL_APPROVAL",
                           execution__cloud_shell__enabled=True, execution__cloud_shell__sandbox_required=False)
        self.assertIn("cloud Shell requires sandbox and independent owner consent", validate_example(bad))

    def test_cloud_shell_requires_consent(self):
        bad = self.variant(execution__profile="CLOUD_SHELL_TRUSTED",
                           execution__cloud_shell__enabled=True,
                           execution__cloud_shell__live_owner_consent_required=False)
        self.assertIn("cloud Shell requires sandbox and independent owner consent", validate_example(bad))

    def test_local_only_denies_cloud_shell(self):
        bad = self.variant(routing__inference_scope="LOCAL_ONLY", routing__cloud_fallback_enabled=False,
                           execution__profile="CLOUD_SHELL_APPROVAL", execution__cloud_shell__enabled=True)
        self.assertIn("cloud Shell profile requires CLOUD_ALLOWED", validate_example(bad))

    def test_local_only_no_cloud_fallback(self):
        bad = self.variant(routing__inference_scope="LOCAL_ONLY")
        self.assertIn("LOCAL_ONLY forbids cloud fallback", validate_example(bad))

    def test_raw_output_disallowed_by_default_contract(self):
        bad = self.variant(privacy__raw_tool_output_to_cloud=True)
        self.assertIn("raw_tool_output_to_cloud cannot be globally enabled", validate_example(bad))

    def test_privacy_consent_not_optional(self):
        bad = self.variant(privacy__recipient_bound_disclosure_consent=False)
        self.assertIn("recipient-bound consent required", validate_example(bad))

    def test_six_agent_limit(self):
        self.assertIn("max_agents must be 1..6", validate_example(self.variant(routing__max_agents=7)))
        self.assertIn("max_agents must be 1..6", validate_example(self.variant(routing__max_agents=True)))

    def test_no_wildcard_bind_in_pilot(self):
        self.assertIn("pilot must be loopback only", validate_example(self.variant(deployment__bind_host="0.0.0.0")))

    def test_pilot_no_auto_start(self):
        self.assertIn("pilot must not auto-start", validate_example(self.variant(deployment__auto_start=True)))


if __name__ == "__main__":
    unittest.main()
