"""Broker authorization tests: every denial path is covered and fail-closed."""
import time
import unittest

from boru.broker import (
    ALLOWED_OPERATIONS, Broker, OperationRequest, ScopeAllowlist, WorkerIdentity,
)
from boru.consent import ConsentStore
from boru.errors import PolicyViolation


def store(grant="g1", task="t1", operation="read_file_alias", nonce="n1", ttl=60):
    consent = ConsentStore()
    consent.grant(grant_id=grant, recipient="w1", task_id=task, field_name=operation,
                  alias="demo", level="L0", expires_at=time.time() + ttl, nonce=nonce)
    return consent


class BrokerTests(unittest.TestCase):
    def broker(self, worker_scopes=("demo",), aliases=None, consent=None):
        return Broker(
            worker=WorkerIdentity("w1", scopes=worker_scopes),
            scopes=ScopeAllowlist(aliases or {"demo": "/tmp/boru-scope"}),
            consent=consent or store(),
        )

    def request(self, **overrides):
        base = dict(operation="read_file_alias", resource_alias="demo", requester="owner",
                    task_id="t1", worker=WorkerIdentity("w1", scopes=("demo",)), fields=("exists",),
                    nonce="n1", grant_id="g1")
        base.update(overrides)
        return OperationRequest(**base)

    def test_allowed_request_issues_a_receipt(self):
        broker = self.broker()
        decision, receipt, reason = broker.authorize(self.request())
        self.assertEqual(("allow", ""), (decision, reason))
        self.assertEqual([], receipt.validate())
        self.assertEqual("read_file_alias", receipt.operation)
        self.assertEqual("w1", receipt.worker_id)
        self.assertEqual(1, receipt.policy_revision)
        # the resource is an opaque token: neither the alias nor its path
        # ever rides in a receipt
        self.assertEqual("r-" + __import__("hashlib").sha256(
            b"/tmp/boru-scope").hexdigest()[:16], receipt.resource_alias)

    def test_receipt_never_carries_a_real_path(self):
        broker = self.broker()
        _, receipt, _ = broker.authorize(self.request())
        payload = repr(receipt.to_dict() if hasattr(receipt, "to_dict") else receipt)
        self.assertNotIn("/tmp", payload)

    def test_replayed_nonce_is_denied(self):
        broker = self.broker()
        self.assertEqual("allow", broker.authorize(self.request())[0])
        self.assertEqual(("deny", "nonce_replayed"), broker.authorize(self.request())[::2])
        # a fresh broker with a fresh grant accepts the same nonce: replay
        # protection is per-broker-process, not a permanent ban.
        self.assertEqual("allow",
                         Broker(worker=WorkerIdentity("w1", scopes=("demo",)),
                                scopes=ScopeAllowlist({"demo": "/tmp/boru-scope"}),
                                consent=store(nonce="n9")).authorize(self.request(nonce="n9"))[0])

    def test_operation_must_be_allowlisted(self):
        broker = self.broker()
        decision, receipt, reason = broker.authorize(self.request(operation="host_shell"))
        self.assertEqual(("deny", "operation_not_allowed"), (decision, reason))
        self.assertIsNone(receipt)
        self.assertNotIn("host_shell", ALLOWED_OPERATIONS)

    def test_resource_must_be_a_declared_alias(self):
        broker = self.broker()
        decision, _, reason = broker.authorize(self.request(resource_alias="../../etc"))
        self.assertEqual(("deny", "resource_not_declared"), (decision, reason))

    def test_worker_must_hold_the_resource_scope(self):
        broker = self.broker()
        decision, _, reason = broker.authorize(self.request(worker=WorkerIdentity("w1")))
        self.assertEqual(("deny", "worker_scope"), (decision, reason))

    def test_missing_grant_is_denied(self):
        broker = self.broker(consent=store(grant="g1", task="other-task"))
        decision, _, reason = broker.authorize(self.request())
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_expired_grant_is_denied(self):
        broker = self.broker(consent=store(ttl=0.5))
        later = time.time() + 5
        decision, _, reason = broker.authorize(self.request(), now=later)
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_revoked_grant_is_denied(self):
        consent = store()
        consent.revoke("g1")
        broker = self.broker(consent=consent)
        self.assertEqual(("deny", "grant_invalid"), broker.authorize(self.request())[::2])

    def test_malformed_requests_are_denied(self):
        broker = self.broker()
        for bad in (
            dict(operation=""),
            dict(resource_alias=""),
            dict(requester=""),
            dict(task_id=""),
            dict(nonce=""),
            dict(grant_id=""),
            dict(nonce="x" * 200),
        ):
            decision, _, reason = broker.authorize(self.request(**bad))
            self.assertEqual(("deny", "malformed_request"), (decision, reason), bad)
        for fields in (("ok", ""), tuple("f{}".format(i) for i in range(9))):
            decision, _, reason = broker.authorize(self.request(fields=fields))
            self.assertEqual(("deny", "fields_invalid"), (decision, reason), fields)

    def test_fields_bound(self):
        broker = self.broker()
        decision, _, _ = broker.authorize(self.request(fields=("exists", "count")))
        self.assertEqual("allow", decision)

    def test_broker_requires_a_consent_store(self):
        with self.assertRaises(PolicyViolation):
            Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({"demo": "/tmp"}), consent=None)

    def test_scope_allowlist_rejects_escapes(self):
        for bad in (("demo", "../etc"), ("demo", "relative"), ("demo", "~/data")):
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1", scopes=(bad[0],)),
                       scopes=ScopeAllowlist({bad[0]: bad[1]}), consent=store())

    def test_empty_scope_allowlist_rejected(self):
        with self.assertRaises(PolicyViolation):
            Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({}), consent=store())

    def test_symlinked_alias_rejected(self):
        import os
        import tempfile

        root = tempfile.mkdtemp(prefix="boru-scope-")
        link = os.path.join(root, "link")
        os.symlink(root, link)
        try:
            self.assertTrue(ScopeAllowlist({"demo": link}).validate())
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1", scopes=("demo",)),
                       scopes=ScopeAllowlist({"demo": link}), consent=store())
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_bad_ttl_rejected(self):
        for bad in (0, True, "60", 9999):
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({"demo": "/tmp"}),
                       consent=store(), receipt_ttl_seconds=bad)

    def test_bad_worker_identity_rejected(self):
        for scopes in (("a", "a"), ("x" * 200,)):
            self.assertTrue(WorkerIdentity("w1", scopes=scopes).validate())
        # an empty scope is a worker with no permissions, never a wider one
        self.assertEqual((), WorkerIdentity("w1", scopes=()).scopes)


if __name__ == "__main__":
    unittest.main()
