"""Offline bridge candidate contract tests. No peer, credentials or network."""
import unittest

from boru.bridge_contracts import EngineManifest, DelegationRoute, check_capability
from boru.errors import ContractError, PolicyViolation


class ManifestTests(unittest.TestCase):
    def test_manifest_roundtrip(self):
        m = EngineManifest("jarvis", ("health", "submit", "cancel"))
        self.assertEqual(m, EngineManifest.from_dict(m.as_dict()))

    def test_manifest_rejects_unknown_fields(self):
        m = EngineManifest("jarvis", ("health",)).as_dict()
        m["grant"] = True
        with self.assertRaises(ContractError):
            EngineManifest.from_dict(m)

    def test_manifest_rejects_invalid_versions(self):
        for version in (True, 0, 2, "1", None):
            with self.subTest(version=version), self.assertRaises(ContractError):
                EngineManifest("jarvis", ("health",), version)

    def test_manifest_rejects_bad_engine_ids(self):
        for name in ("", "../jarvis", "a b", "x\n", "a"*65, None):
            with self.subTest(name=name), self.assertRaises(ContractError):
                EngineManifest(name, ("health",))

    def test_manifest_rejects_bad_operations(self):
        for ops in ((), ("shell",), ("health", "health"), ([],), ["health"]):
            with self.subTest(ops=ops), self.assertRaises(ContractError):
                EngineManifest("jarvis", ops)

    def test_manifest_wire_requires_bounded_list(self):
        for operations in ("health", [], ["health"]*100, ("health",)):
            with self.subTest(operations=operations), self.assertRaises(ContractError):
                EngineManifest.from_dict({"engine_id": "jarvis", "operations": operations,
                                          "schema_version": 1})

    def test_unsupported_operation_denied(self):
        m = EngineManifest("boru", ("health",))
        self.assertIsNone(check_capability(m, "health"))
        for op in ("submit", "shell", []):
            with self.assertRaises(PolicyViolation):
                check_capability(m, op)


class DelegationTests(unittest.TestCase):
    def test_owner_and_task_preserved(self):
        a = DelegationRoute.start("task1", "jarvis")
        b = a.forward("boru")
        self.assertEqual(("jarvis", "boru"), b.visited)
        self.assertEqual(("jarvis",), a.visited)
        self.assertEqual(("task1", "jarvis"), (b.task_id, b.owner_id))

    def test_cycle_denied(self):
        route = DelegationRoute.start("task1", "jarvis").forward("boru")
        with self.assertRaises(PolicyViolation):
            route.forward("jarvis")

    def test_limit_exhausted(self):
        route = DelegationRoute.start("task1", "boru", 1).forward("jarvis")
        with self.assertRaises(PolicyViolation):
            route.forward("codex")

    def test_zero_hops_is_valid_but_denies_forwarding(self):
        with self.assertRaises(PolicyViolation):
            DelegationRoute.start("task1", "boru", 0).forward("jarvis")

    def test_invalid_limits_and_histories(self):
        for limit in (True, -1, 7, "1"):
            with self.assertRaises(ContractError):
                DelegationRoute.start("task1", "boru", limit)
        for history in ((), ("jarvis",), ("boru", "boru"), ["boru"], ("boru", [])):
            with self.assertRaises(ContractError):
                DelegationRoute("task1", "boru", history)

    def test_invalid_target_denied(self):
        with self.assertRaises(ContractError):
            DelegationRoute.start("task1", "boru").forward("../jarvis")


if __name__ == "__main__":
    unittest.main()
