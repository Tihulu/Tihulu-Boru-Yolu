"""Cloud-Shell grant contract tests (P6 decisions only; nothing executes)."""
import time
import unittest

from boru.audit import RejectionLedger
from boru.errors import PolicyViolation
from boru.sandbox import MAX_CALLS, MAX_MINUTES, SANDBOX_OPERATIONS, SandboxBroker, SandboxGrant


def grant(**overrides):
    base = dict(grant_id="g1", owner_id="owner", recipient_provider="openai",
                recipient_model="gpt-test", task_id="t1", sandbox_id="sbx-1",
                operation_types=("read_file_alias",), resource_aliases=("demo",),
                field_disclosures=("exists",), issued_at=time.time(),
                expires_at=time.time() + 60, max_calls=2, nonce="n1")
    base.update(overrides)
    return SandboxGrant(**base)


class GrantValidationTests(unittest.TestCase):
    def test_host_operations_are_absent(self):
        for forbidden in ("host_shell", "run_command", "exec", "delete_file", "send_email"):
            self.assertNotIn(forbidden, SANDBOX_OPERATIONS)
        for operation in SANDBOX_OPERATIONS:
            item = grant(operation_types=(operation,))
            self.assertEqual([], item.validate(), operation)

    def test_bad_grants_rejected(self):
        for bad in (dict(grant_id=""), dict(owner_id=""), dict(recipient_provider=""),
                    dict(recipient_model=""), dict(task_id=""), dict(sandbox_id=""), dict(nonce=""),
                    dict(operation_types=()), dict(operation_types=("host_shell",)),
                    dict(resource_aliases=()), dict(resource_aliases=("../etc",)),
                    dict(max_calls=0), dict(max_calls=True), dict(max_calls=MAX_CALLS + 1),
                    dict(expires_at=time.time() - 1), dict(revoked="yes")):
            item = grant(**bad)
            self.assertTrue(item.validate(), bad)

    def test_lifetime_cap(self):
        too_long = grant(expires_at=time.time() + (MAX_MINUTES + 5) * 60)
        self.assertTrue(too_long.validate())
        self.assertEqual([], grant().validate())


class SandboxBrokerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = RejectionLedger()
        self.broker = SandboxBroker(worker_scopes=("sandbox-a",), ledger=self.ledger)

    def tearDown(self):
        self.ledger.close()

    def check(self, item=None, *, operation="read_file_alias", alias="demo",
              worker_scope="sandbox-a", now=None, sandbox_available=True, field_requested=None):
        item = item if item is not None else grant()
        allowed, reason = self.broker.authorize(
            item, operation=operation, alias=alias, worker_scope=worker_scope, now=now,
            sandbox_available=sandbox_available, field_requested=field_requested)
        return allowed, reason

    def test_recipient_bound_denials(self):
        cases = (
            (grant(operation_types=("read_file_alias",)), "list_dir_alias", "demo", "sandbox-a",
             "operation_not_granted"),
            (grant(), "read_file_alias", "other", "sandbox-a", "resource_not_granted"),
            (grant(), "read_file_alias", "demo", "sandbox-b", "worker_scope"),
            (grant(), "read_file_alias", "demo", "sandbox-a", "field_not_granted"),
            (grant(issued_at=time.time() - 120, expires_at=time.time() - 60), "read_file_alias",
             "demo", "sandbox-a", "grant_expired"),
            (grant(nonce=""), "read_file_alias", "demo", "sandbox-a", "grant_invalid"),
        )
        for item, operation, alias, scope, reason in cases:
            allowed, got = self.check(item, operation=operation, alias=alias, worker_scope=scope,
                                      field_requested="size" if reason == "field_not_granted" else None)
            self.assertEqual((False, reason), (allowed, got), reason)

    def test_no_sandbox_means_denial(self):
        self.assertEqual((False, "sandbox_unavailable"), self.check(sandbox_available=False))

    def test_sandbox_available_allows_and_counts(self):
        self.assertEqual((True, ""), self.check())
        self.assertEqual(1, self.broker.calls_used("g1"))

    def test_nonce_replay_is_denied(self):
        first = grant(nonce="n1")
        second = grant(nonce="n2")
        self.check(first)
        self.assertEqual((False, "nonce_replayed"), self.check(first))
        self.assertEqual((True, ""), self.check(second))

    def test_call_ceiling_is_enforced(self):
        item = grant(max_calls=1)
        self.assertEqual((True, ""), self.check(item))
        self.assertEqual((False, "grant_exhausted"), self.check(item))

    def test_revocation(self):
        item = grant()
        self.broker.revoke("g1")
        self.assertEqual((False, "grant_revoked"), self.check(item))

    def test_denials_are_recorded(self):
        self.check(operation="list_dir_alias")
        rows = [(row["reason"], row["detail_kind"]) for row in self.ledger.recent(8)]
        self.assertIn(("operation_not_granted", "list_dir_alias"), rows)

    def test_bad_policy_revision_rejected(self):
        with self.assertRaises(PolicyViolation):
            SandboxBroker(worker_scopes=("sandbox-a",), ledger=self.ledger, policy_revision=2)


if __name__ == "__main__":
    unittest.main()
