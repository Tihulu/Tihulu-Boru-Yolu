"""Adversarial walkthroughs for the security-critical rewrites.

Each test drives the real modules with inputs no honest caller would send:
control-character targets, directory references, key-less workers, token
swaps, ambiguous grant ids and replayed nonces. The expectation is always the
fail-closed one.
"""
import dataclasses
import os
import stat
import tempfile
import time
import unittest

from boru.authorization import AuthorizationReceipt
from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity
from boru.consent import ConsentStore
from boru.errors import ConfigurationError, PolicyViolation
from boru.executor import LocalExecutor
from boru.workers import WorkerRegistry

KEY = bytes(range(32))


class AdversarialWalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-adv-")
        os.chmod(self.root, stat.S_IRWXU)
        self.alias_dir = os.path.join(self.root, "data")
        os.makedirs(self.alias_dir)
        os.chmod(self.alias_dir, stat.S_IRWXU)
        with open(os.path.join(self.alias_dir, "note.txt"), "w", encoding="utf-8") as handle:
            handle.write("alpha\nbeta\ngamma\n")
        os.mkdir(os.path.join(self.alias_dir, "nested"))
        os.symlink(os.path.join(self.alias_dir, "note.txt"),
                   os.path.join(self.alias_dir, "link.txt"))
        self.scopes = ScopeAllowlist({"demo": self.alias_dir})
        self.worker = WorkerIdentity("w", scopes=("demo",))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def authorise(self, consent, grant, task, operation, fields, target=None):
        broker = Broker(worker=self.worker, scopes=self.scopes, consent=consent,
                        consent_recipient="w", authorization_key=KEY)
        request = OperationRequest(operation=operation, resource_alias="demo", requester="owner",
                                   task_id=task, worker=self.worker, fields=fields, nonce="n",
                                   grant_id=grant, target=target)
        return broker.authorize(request, requested_fields=fields)

    def grant_for(self, task, operation="probe_path_alias", level="L0", alias="demo"):
        consent = ConsentStore()
        consent.grant(grant_id="g-" + task, recipient="w", task_id=task, field_name=operation,
                      alias=alias, level=level, expires_at=time.time() + 60, nonce="n")
        return consent

    def test_recipient_bound_grants_never_cross(self):
        store = ConsentStore()
        # a grant id is globally unique: one id, one recipient
        store.grant(grant_id="g-a", recipient="a", task_id="t", field_name="probe", alias="demo",
                    level="L0", expires_at=time.time() + 60, nonce="n1")
        store.grant(grant_id="g-b", recipient="b", task_id="t", field_name="probe", alias="demo",
                    level="L0", expires_at=time.time() + 60, nonce="n2")
        self.assertTrue(store.check(grant_id="g-a", recipient="a", task_id="t",
                                    field_name="probe", alias="demo", nonce="n1"))
        self.assertTrue(store.check(grant_id="g-b", recipient="b", task_id="t",
                                    field_name="probe", alias="demo", nonce="n2"))
        # the other recipient's grant never serves this one
        self.assertFalse(store.check(grant_id="g-a", recipient="b", task_id="t",
                                     field_name="probe", alias="demo", nonce="n1"))
        # a check that cannot name its recipient never matches any grant:
        # the recipient is mandatory, so an unnamed one refuses (F03)
        self.assertFalse(store.check(grant_id="g", recipient="", task_id="t",
                                     field_name="probe", alias="demo", nonce="n3"))
        with self.assertRaises(TypeError):
            store.check(grant_id="g-a", task_id="t", field_name="probe",
                        alias="demo", nonce="n1")

    def test_nonce_cannot_be_replayed(self):
        consent = self.grant_for("t2")
        decision, receipt, _ = self.authorise(consent, "g-t2", "t2", "probe_path_alias", ("exists",))
        self.assertEqual("allow", decision)
        self.assertIsNotNone(receipt)
        decision2, _, _ = self.authorise(consent, "g-t2", "t2", "probe_path_alias", ("exists",))
        self.assertEqual("deny", decision2)

    def test_control_and_path_targets_never_reach_a_receipt(self):
        consent = self.grant_for("t3")
        for bad in ("note.txt\x00", "note.txt\n", "/etc/passwd", "..", ".",
                    "./note.txt", "nested/../note.txt"):
            decision, receipt, reason = self.authorise(consent, "g-t3", "t3",
                                                       "probe_path_alias", ("exists",),
                                                       target=bad)
            self.assertEqual("deny", decision, bad)
            self.assertIsNone(receipt, bad)
            self.assertTrue(reason, bad)

    def test_symlinked_target_is_not_followed(self):
        consent = self.grant_for("t4")
        decision, receipt, _ = self.authorise(consent, "g-t4", "t4", "probe_path_alias",
                                              ("exists",), target="link.txt")
        self.assertEqual("allow", decision)
        executor = LocalExecutor(self.scopes, authorization_key=KEY)
        with self.assertRaises(PolicyViolation):
            executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_worker_without_an_authorization_key_refuses_everything(self):
        consent = self.grant_for("t5")
        _, receipt, _ = self.authorise(consent, "g-t5", "t5", "probe_path_alias", ("exists",))
        keyless = LocalExecutor(self.scopes)
        with self.assertRaises(PolicyViolation):
            keyless.acquire(receipt, fields=("exists",), now=time.time())

    def test_a_receipt_bound_to_another_resource_is_refused(self):
        second = os.path.join(self.root, "second")
        os.makedirs(second)
        other = ScopeAllowlist({"other": second})
        consent = self.grant_for("t6")
        _, receipt, _ = self.authorise(consent, "g-t6", "t6", "probe_path_alias", ("exists",))
        swapped = dataclasses.replace(receipt, resource_alias=other.token_for("other"))
        with self.assertRaises(PolicyViolation):
            swapped.verify(KEY, now=time.time(), requested_fields=("exists",))

    def test_registry_authenticated_dispatch_and_consumed_nonce(self):
        worker_dir = os.path.join(self.root, "workers")
        os.makedirs(worker_dir)
        os.chmod(worker_dir, stat.S_IRWXU)
        registry = WorkerRegistry(worker_dir)
        registry.create("w1", ("demo",))
        secret = registry.secret_for("w1")
        consent = ConsentStore()
        consent.grant(grant_id="g7", recipient="w1", task_id="t7",
                      field_name="probe_path_alias", alias="demo", level="L0",
                      expires_at=time.time() + 60, nonce="n")
        broker = Broker(worker=WorkerIdentity("w1", scopes=("demo",)), scopes=self.scopes,
                        consent=consent, consent_recipient="w1", registry=registry,
                        worker_secret=secret)
        request = OperationRequest(operation="probe_path_alias", resource_alias="demo",
                                   requester="owner", task_id="t7",
                                   worker=WorkerIdentity("w1", scopes=("demo",)),
                                   fields=("exists",), nonce="n", grant_id="g7")
        self.assertEqual("allow", broker.authorize(request, requested_fields=("exists",))[0])
        replay = OperationRequest(operation="probe_path_alias", resource_alias="demo",
                                  requester="owner", task_id="t7",
                                  worker=WorkerIdentity("w1", scopes=("demo",)),
                                  fields=("exists",), nonce="n", grant_id="g7")
        self.assertEqual("deny", broker.authorize(replay, requested_fields=("exists",))[0])

    def test_registry_refuses_a_path_like_scope(self):
        worker_dir = os.path.join(self.root, "workers")
        os.makedirs(worker_dir)
        os.chmod(worker_dir, stat.S_IRWXU)
        registry = WorkerRegistry(worker_dir)
        with self.assertRaises(ConfigurationError):
            registry.create("w2", ("/etc",))


if __name__ == "__main__":
    unittest.main()
