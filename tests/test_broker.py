"""Broker authorization tests: every denial path is covered and fail-closed."""
import time
import unittest

from boru.broker import (
    ALLOWED_OPERATIONS, Broker, OperationRequest, ScopeAllowlist, WorkerIdentity,
)
from boru.authorization import AuthorizationReceipt, derive_key, sign
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
            consent=consent or store(), consent_recipient="w1",
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
                                consent=store(nonce="n9"),
                                consent_recipient="w1").authorize(self.request(nonce="n9"))[0])

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
            Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({"demo": "/tmp"}), consent=None,
                   consent_recipient="w1")

    def test_scope_allowlist_rejects_escapes(self):
        for bad in (("demo", "../etc"), ("demo", "relative"), ("demo", "~/data")):
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1", scopes=(bad[0],)),
                       scopes=ScopeAllowlist({bad[0]: bad[1]}), consent=store(),
                       consent_recipient="w1")

    def test_empty_scope_allowlist_rejected(self):
        with self.assertRaises(PolicyViolation):
            Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({}), consent=store(),
                   consent_recipient="w1")

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
                       scopes=ScopeAllowlist({"demo": link}), consent=store(),
                       consent_recipient="w1")
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_bad_ttl_rejected(self):
        for bad in (0, True, "60", 9999):
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1"), scopes=ScopeAllowlist({"demo": "/tmp"}),
                       consent=store(), consent_recipient="w1", receipt_ttl_seconds=bad)

    def test_bad_worker_identity_rejected(self):
        for scopes in (("a", "a"), ("x" * 200,)):
            self.assertTrue(WorkerIdentity("w1", scopes=scopes).validate())
        # an empty scope is a worker with no permissions, never a wider one
        self.assertEqual((), WorkerIdentity("w1", scopes=()).scopes)


class ReceiptTagCoverageTests(unittest.TestCase):
    """Every field a receipt carries is authenticated by its tag.

    The tag previously covered the operation, alias, worker, grant, nonce,
    expiry, fields and target but **not `issued_at`**, so a receipt's issue
    timestamp could be rewritten in transit without failing the tag. It is now
    part of the signed payload.
    """

    KEY = "a" * 64

    def setUp(self):
        self.key = derive_key(self.KEY)
        self.now = 1_700_000_000.0
        self.token = "r-" + "ab" * 8
        self.fields = ("exists",)

    def _tag(self, **over):
        base = dict(task_id="t1", operation="probe_path_alias", alias=self.token,
                    worker_id="w1", grant_id="g1", nonce="n1", expires_at=self.now + 60,
                    fields=self.fields, target="", issued_at=self.now)
        base.update(over)
        return sign(self.key, **base)

    def _receipt(self, **over):
        base = dict(receipt_id=self.token, operation="probe_path_alias",
                    resource_alias=self.token, task_id="t1", worker_id="w1",
                    grant_id="g1", issued_at=self.now, expires_at=self.now + 60,
                    nonce="n1", allowed_fields=self.fields, target="",
                    decision="allow", authentication_tag=self._tag())
        base.update(over)
        return AuthorizationReceipt(**base)

    def _verify(self, receipt):
        return receipt.verify(self.key, now=self.now, requested_fields=self.fields)

    def test_a_well_formed_receipt_verifies(self):
        self.assertIsNone(self._verify(self._receipt()))

    def test_a_tampered_issued_at_is_refused_even_with_the_valid_tag(self):
        # The attacker keeps the genuine tag and rewrites only issued_at.
        receipt = self._receipt()
        for tampered in (self.now + 10, self.now + 30, self.now - 999):
            forged = AuthorizationReceipt(
                receipt_id=receipt.receipt_id, operation=receipt.operation,
                resource_alias=receipt.resource_alias, task_id=receipt.task_id,
                worker_id=receipt.worker_id, grant_id=receipt.grant_id,
                issued_at=tampered, expires_at=receipt.expires_at,
                nonce=receipt.nonce, allowed_fields=receipt.allowed_fields,
                target=receipt.target, decision=receipt.decision,
                authentication_tag=receipt.authentication_tag)
            with self.assertRaises(PolicyViolation) as ctx:
                self._verify(forged)
            self.assertIn("authentication failed", str(ctx.exception))

    def test_issued_at_rounding_cannot_forge_a_tag(self):
        # A float re-encode of the same instant must still verify, but a
        # different instant must not.
        same = self._receipt()
        self.assertIsNone(self._verify(same))
        other = self._receipt(issued_at=self.now,
                              authentication_tag=self._tag(issued_at=self.now + 0.000001))
        with self.assertRaises(PolicyViolation):
            self._verify(other)

    def test_the_broker_issues_a_receipt_whose_tag_covers_issued_at(self):
        # A real broker-issued receipt verifies, and one whose issued_at is
        # shifted while its genuine tag is kept is refused.
        broker = Broker(worker=WorkerIdentity("w1", scopes=("demo",)),
                        scopes=ScopeAllowlist({"demo": "/tmp"}),
                        consent=ConsentStore(), consent_recipient="w1")
        consent = broker.consent
        consent.grant(grant_id="g", recipient="w1", task_id="t",
                      field_name="probe_path_alias", alias="demo", level="L0",
                      expires_at=time.time() + 60, nonce="n")
        decision, receipt, _reason = broker.authorize(OperationRequest(
            operation="probe_path_alias", resource_alias="demo", requester="owner",
            task_id="t", worker=WorkerIdentity("w1", scopes=("demo",)),
            fields=("exists",), nonce="n", grant_id="g"), requested_fields=("exists",))
        self.assertEqual("allow", decision)
        self.assertIsNotNone(receipt)
        forged = AuthorizationReceipt(
            receipt_id=receipt.receipt_id, operation=receipt.operation,
            resource_alias=receipt.resource_alias, task_id=receipt.task_id,
            worker_id=receipt.worker_id, grant_id=receipt.grant_id,
            issued_at=receipt.issued_at + 5, expires_at=receipt.expires_at,
            nonce=receipt.nonce, allowed_fields=receipt.allowed_fields,
            target=receipt.target, decision=receipt.decision,
            authentication_tag=receipt.authentication_tag)
        with self.assertRaises(PolicyViolation) as ctx:
            forged.verify(broker.key, now=time.time(),
                          requested_fields=receipt.allowed_fields)
        self.assertIn("authentication failed", str(ctx.exception))
        # And the untouched receipt still verifies.
        receipt.verify(broker.key, now=time.time(),
                       requested_fields=receipt.allowed_fields)


if __name__ == "__main__":
    unittest.main()
