"""Authenticated loopback broker service tests."""
import os
import stat
import tempfile
import time
import unittest

from boru.audit import RejectionLedger
from boru.broker import Broker, ScopeAllowlist, WorkerIdentity
from boru.broker_service import BrokerService, ask
from boru.consent import ConsentStore
from boru.errors import PolicyViolation
from boru.workers import WorkerRegistry


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-svc-")
        os.chmod(self.root, stat.S_IRWXU)
        self.worker_dir = os.path.join(self.root, "workers")
        self.alias = os.path.join(self.root, "demo")
        os.makedirs(self.worker_dir)
        os.makedirs(self.alias)
        os.chmod(self.worker_dir, stat.S_IRWXU)
        os.chmod(self.alias, stat.S_IRWXU)
        self.registry = WorkerRegistry(self.worker_dir)
        self.registry.create("w1", (self.alias,))
        self.secret = self.registry.secret_for("w1")
        self.consent = ConsentStore(thread_safe=True)
        self.consent.grant(grant_id="g", recipient="w1", task_id="t1",
                           field_name="probe_path_alias", level="L0",
                           expires_at=time.time() + 60, nonce="n1")
        self.ledger = RejectionLedger()
        self.broker = Broker(worker=WorkerIdentity("w1", scopes=(self.alias,)),
                             scopes=ScopeAllowlist({self.alias: self.alias}),
                             consent=self.consent, consent_recipient="w1",
                             worker_registry=self.registry, worker_secret=self.secret,
                             audit=self.ledger)
        self.service = BrokerService(self.broker, self.registry, "w1", self.secret)
        self.host, self.port = self.service.start()
        self.body = {"operation": "probe_path_alias", "resource_alias": self.alias,
                     "requester": "owner", "task_id": "t1", "worker": "w1",
                     "fields": ["exists"], "nonce": "n1", "grant_id": "g"}

    def tearDown(self):
        self.service.stop()
        self.ledger.close()
        self.consent.close()
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_authenticated_worker_is_allowed(self):
        reply = ask(self.service, {"worker_id": "w1", "secret": self.secret, "request": self.body})
        self.assertEqual("allow", reply["decision"])
        self.assertEqual("", reply["reason"])

    def test_wrong_secret_is_denied(self):
        reply = ask(self.service, {"worker_id": "w1", "secret": "not-the-secret",
                                   "request": self.body})
        self.assertEqual("deny", reply["decision"])
        self.assertEqual("worker_invalid", reply["reason"])

    def test_unknown_worker_is_denied(self):
        reply = ask(self.service, {"worker_id": "ghost", "secret": self.secret,
                                   "request": self.body})
        self.assertEqual("deny", reply["decision"])
        self.assertEqual("worker_invalid", reply["reason"])

    def test_revoked_worker_is_denied(self):
        reply = ask(self.service, {"worker_id": "w1", "secret": self.secret, "request": self.body})
        self.assertEqual("allow", reply["decision"])
        self.registry.revoke("w1")
        body = dict(self.body, nonce="n2")
        reply = ask(self.service, {"worker_id": "w1", "secret": self.secret, "request": body})
        self.assertEqual("deny", reply["decision"])
        self.assertEqual("worker_invalid", reply["reason"])

    def test_broker_denial_flows_through(self):
        body = dict(self.body, operation="host_shell")
        reply = ask(self.service, {"worker_id": "w1", "secret": self.secret, "request": body})
        self.assertEqual("deny", reply["decision"])
        self.assertEqual("operation_not_allowed", reply["reason"])

    def test_malformed_payload_is_denied(self):
        reply = ask(self.service, {"worker_id": "w1", "secret": self.secret, "request": "not-a-dict"})
        self.assertEqual("deny", reply["decision"])
        self.assertEqual("malformed_request", reply["reason"])

    def test_public_bind_is_refused(self):
        with self.assertRaises(PolicyViolation):
            BrokerService(self.broker, self.registry, "w1", self.secret, host="0.0.0.0")

    def test_missing_secret_is_refused(self):
        with self.assertRaises(PolicyViolation):
            BrokerService(self.broker, self.registry, "w1", "")


if __name__ == "__main__":
    unittest.main()
