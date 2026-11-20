"""Privacy Bridge gate tests: fail-closed typed release and adversarial input."""
import time
import unittest

from boru.errors import PolicyViolation
from boru.privacy import ConsentStore, DisclosureGate, DisclosureRequest, GateDecision, LEVEL_FIELDS


def request(level, fields, payload, recipient="cloud", task_id="t1"):
    return DisclosureRequest(task_id=task_id, recipient=recipient, level=level, fields=tuple(fields), payload=payload)


class GateTests(unittest.TestCase):
    def gate(self, policy="MINIMUM_NECESSARY", **kwargs):
        return DisclosureGate(policy, **kwargs)

    def test_bad_policy_and_limits_rejected(self):
        for bad in ("ANYTHING", "", None):
            with self.assertRaises(PolicyViolation):
                DisclosureGate(bad)
        for bad in (0, True, 40):
            with self.assertRaises(PolicyViolation):
                DisclosureGate("MINIMUM_NECESSARY", max_result_fields=bad)

    def test_l0_release_is_minimal(self):
        decision, payload, reason = self.gate().release(
            request("L0", ("passed", "failed"), {"passed": 12, "failed": 1, "everything": "else"}))
        self.assertEqual(GateDecision.RELEASE, decision)
        self.assertEqual({"passed": 12, "failed": 1}, payload)
        self.assertEqual("", reason or "")

    def test_private_field_always_refused(self):
        for name in sorted({"raw_stdout", "environment", "home_path", "api_key", "directory_listing"}):
            decision, _, reason = self.gate().release(
                request("L0", ("status", name), {"status": "ok", name: "x"}))
            self.assertEqual(GateDecision.DENY, decision, name)
            self.assertEqual("private_field_refused", reason)

    def test_field_not_allowed_for_level(self):
        decision, _, reason = self.gate().release(request("L0", ("excerpt",), {"excerpt": "text"}))
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("field_not_allowed_for_level", reason)

    def test_malformed_request_denied(self):
        for bad in (
            request("L0", (), {}),
            request("L0", ("status",), {"status": "ok"}, recipient=""),
            request("L0", ("status",), {"status": "ok"}, task_id=""),
            request("L0", ("status", "status"), {"status": "ok"}),
            request("L9", ("status",), {"status": "ok"}),
        ):
            decision, _, reason = self.gate().release(bad)
            self.assertEqual(GateDecision.DENY, decision, bad)
            self.assertEqual("malformed_request", reason)

    def test_missing_field_holds(self):
        decision, _, reason = self.gate().release(request("L0", ("count",), {}))
        self.assertEqual(GateDecision.HOLD, decision)
        self.assertEqual("field_unavailable", reason)

    def test_payload_shape_enforced(self):
        for payload, expected in (
            ({"status": "x" * 600}, "payload_rejected"),
            ({"status": {"nested": {"deeper": {"too": "deep"}}}}, "payload_rejected"),
            ({"status": float("nan")}, "payload_rejected"),
            ({"status": object()}, "payload_rejected"),
            ({"status": "line\nbreak"}, "payload_rejected"),
            ({"status": 2 ** 40}, "payload_rejected"),
        ):
            decision, _, reason = self.gate().release(request("L0", ("status",), payload))
            self.assertEqual(GateDecision.DENY, decision, payload)
            self.assertEqual(expected, reason)

    def test_bounded_object_payload_allowed(self):
        decision, payload, _ = self.gate().release(
            request("L0", ("count",), {"count": {"passed": 3, "failed": 0}}))
        self.assertEqual(GateDecision.RELEASE, decision)
        self.assertEqual({"count": {"passed": 3, "failed": 0}}, payload)

    def test_max_result_fields_enforced(self):
        decision, _, reason = self.gate(max_result_fields=2).release(
            request("L0", ("status", "count", "passed"), {"status": "ok", "count": 2, "passed": True}))
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("max_result_fields_exceeded", reason)

    def test_l1_requires_non_minimal_names(self):
        decision, payload, reason = self.gate().release(
            request("L1", ("dependency_name",), {"dependency_name": "example-package"}))
        self.assertEqual(GateDecision.RELEASE, decision)
        self.assertEqual({"dependency_name": "example-package"}, payload)

    def test_l2_requires_scoped_approved_policy(self):
        payload = {"excerpt": "short", "grant_id": "g", "nonce": "n"}
        decision, _, reason = self.gate("MINIMUM_NECESSARY").release(request("L2", ("excerpt",), payload))
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("policy_requires_scoped_approved", reason)

    def test_l2_needs_a_matching_grant(self):
        gate = self.gate("SCOPED_APPROVED")
        consent = ConsentStore()
        consent.grant(grant_id="g1", recipient="cloud", task_id="t1", field_name="excerpt",
                      level="L2", expires_at=time.time() + 60, nonce="n1")
        payload = {"excerpt": "short", "grant_id": "g1", "nonce": "n1"}
        decision, released, reason = gate.release(request("L2", ("excerpt",), payload), consent)
        self.assertEqual(GateDecision.RELEASE, decision)
        self.assertEqual({"excerpt": "short"}, released)
        # replay of the same nonce is refused
        decision, _, reason = gate.release(request("L2", ("excerpt",), payload), consent)
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("grant_invalid", reason)

    def test_grant_bound_to_recipient_task_and_field(self):
        gate = self.gate("SCOPED_APPROVED")
        consent = ConsentStore()
        consent.grant(grant_id="g2", recipient="cloud", task_id="t1", field_name="excerpt",
                      level="L2", expires_at=time.time() + 60, nonce="n2")
        base = {"excerpt": "short", "grant_id": "g2", "nonce": "n2"}
        for wrong in (
            request("L2", ("excerpt",), base, recipient="other"),
            request("L2", ("excerpt",), base, task_id="t2"),
        ):
            decision, _, reason = gate.release(wrong, consent)
            self.assertEqual(GateDecision.DENY, decision, wrong)
            self.assertEqual("grant_invalid", reason)

    def test_expired_and_revoked_grants_deny(self):
        gate = self.gate("SCOPED_APPROVED")
        consent = ConsentStore()
        consent.grant(grant_id="g3", recipient="cloud", task_id="t1", field_name="excerpt",
                      level="L2", expires_at=time.time() + 1, nonce="n3")
        payload = {"excerpt": "short", "grant_id": "g3", "nonce": "n3"}
        gate.release(request("L2", ("excerpt",), payload), consent, now=time.time() + 10)
        consent.grant(grant_id="g4", recipient="cloud", task_id="t1", field_name="excerpt",
                      level="L2", expires_at=time.time() + 60, nonce="n4")
        payload = {"excerpt": "short", "grant_id": "g4", "nonce": "n4"}
        consent.revoke("g4")
        decision, _, reason = gate.release(request("L2", ("excerpt",), payload), consent)
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("grant_invalid", reason)

    def test_missing_consent_store_denies(self):
        gate = self.gate("SCOPED_APPROVED")
        payload = {"excerpt": "short", "grant_id": "g5", "nonce": "n5"}
        decision, _, reason = gate.release(request("L2", ("excerpt",), payload), None)
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("consent_store_unavailable", reason)

    def test_raw_release_is_never_allowed(self):
        gate = DisclosureGate("SCOPED_APPROVED", allow_raw=True)
        decision, _, reason = gate.release(request("L0", ("status",), {"status": "ok"}))
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual("raw_release_refused", reason)

    def test_bad_grants_rejected(self):
        consent = ConsentStore()
        for bad in (
            dict(grant_id="", recipient="r", task_id="t", field_name="f", level="L2",
                 expires_at=time.time() + 1, nonce="n"),
            dict(grant_id="g", recipient="r", task_id="t", field_name="f", level="L9",
                 expires_at=time.time() + 1, nonce="n"),
            dict(grant_id="g", recipient="r", task_id="t", field_name="f", level="L2",
                 expires_at=time.time() + 1, nonce=5),
        ):
            with self.assertRaises((PolicyViolation, TypeError)):
                consent.grant(**bad)

    def test_duplicate_grant_id_refused(self):
        consent = ConsentStore()
        kwargs = dict(grant_id="dup", recipient="r", task_id="t", field_name="f",
                      level="L2", expires_at=time.time() + 1, nonce="n")
        consent.grant(**kwargs)
        with self.assertRaises(PolicyViolation):
            consent.grant(**kwargs)

    def test_level_definitions_are_typing_only(self):
        self.assertNotIn("raw_stdout", tuple(LEVEL_FIELDS["L0"]))
        for level in LEVEL_FIELDS:
            self.assertTrue(all(name.isidentifier() for name in LEVEL_FIELDS[level]))


if __name__ == "__main__":
    unittest.main()
