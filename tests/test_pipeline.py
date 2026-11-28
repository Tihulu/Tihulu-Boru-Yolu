"""End-to-end local disclosure pipeline tests (P5): every denial path holds."""
import os
import stat
import tempfile
import time
import unittest

from boru.audit import RejectionLedger
from boru.broker import Broker, ScopeAllowlist, WorkerIdentity
from boru.broker_service import BrokerService
from boru.consent import ConsentStore
from boru.pipeline import WORKER_ID, DisclosurePipeline
from boru.workers import WorkerRegistry

ALIAS = "demo"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-pipeline-")
        os.chmod(self.root, stat.S_IRWXU)
        self.worker_dir = os.path.join(self.root, "workers")
        self.alias_dir = os.path.join(self.root, ALIAS)
        os.makedirs(self.worker_dir)
        os.makedirs(self.alias_dir)
        os.chmod(self.worker_dir, stat.S_IRWXU)
        os.chmod(self.alias_dir, stat.S_IRWXU)
        with open(os.path.join(self.alias_dir, "secret-note.txt"), "w", encoding="utf-8") as handle:
            handle.write("private content\n")
        self.aliases = {ALIAS: self.alias_dir}
        self.workers = WorkerRegistry(self.worker_dir)
        self.workers.create(WORKER_ID, (ALIAS,))
        self.consent = ConsentStore()
        self.ledger = RejectionLedger()
        self.pipeline = DisclosurePipeline(worker=self.workers, consent=self.consent,
                                           aliases=self.aliases, ledger=self.ledger)

    def tearDown(self):
        self.workers.delete(WORKER_ID)
        shutil_rmtree(self.root)

    def grant(self, task_id, operation="probe_path_alias", level="L0", ttl=60):
        self.consent.grant(grant_id="g-{}".format(task_id), recipient=WORKER_ID, task_id=task_id,
                           field_name=operation, alias=ALIAS, level=level,
                           expires_at=time.time() + ttl,
                           nonce="n-{}-{}".format(task_id, operation))

    def test_l0_release_carries_typed_fields_only(self):
        self.grant("t1")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t1", operation="probe_path_alias", alias=ALIAS,
            fields=("exists", "type"), recipient="owner")
        self.assertEqual(("release", ""), (decision, reason))
        self.assertEqual({"exists": True, "type": "dir"}, payload)
        self.assertNotIn("secret-note", repr(payload))
        self.assertNotIn(self.root, repr(payload))

    def test_order_returns_a_count_not_names(self):
        self.grant("t2", operation="list_dir_alias")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t2", operation="list_dir_alias", alias=ALIAS,
            fields=("entry_count",), recipient="owner")
        self.assertEqual("release", decision)
        self.assertIn("entry_count", payload)
        self.assertNotIn("secret-note.txt", repr(payload))

    def test_l1_read_reports_real_metadata_only(self):
        self.grant("t11", operation="read_file_alias", level="L1")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t11", operation="read_file_alias", alias=ALIAS,
            fields=("size", "line_count"), recipient="owner", level="L1",
            target="secret-note.txt")
        self.assertEqual(("release", ""), (decision, reason))
        self.assertEqual({"size": 16, "line_count": 1}, payload)
        self.assertNotIn("private content", repr(payload))

    def test_missing_grant_denies(self):
        decision, payload, reason = self.pipeline.disclose(
            task_id="t9", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))
        self.assertEqual({}, payload)
        self.assertIn(("broker", "t9", "grant_invalid"),
                      [(row["category"], row["subject"], row["reason"]) for row in self.ledger.recent(8)])

    def test_expired_grant_denies(self):
        self.grant("t3", ttl=0.2)
        later = time.time() + 5
        decision, _, reason = self.pipeline.disclose(
            task_id="t3", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner", now=later)
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_operation_not_granted_denies(self):
        self.grant("t4", operation="probe_path_alias")
        decision, _, reason = self.pipeline.disclose(
            task_id="t4", operation="read_file_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        # the operation is allowed in principle, but the consent grant names a
        # different operation, so the broker denies it
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_l1_requires_a_wider_declaration(self):
        self.grant("t5")
        decision, _, reason = self.pipeline.disclose(
            task_id="t5", operation="probe_path_alias", alias=ALIAS,
            fields=("size",), recipient="owner")
        self.assertEqual(("deny", "field_not_allowed_for_level"), (decision, reason))

    def test_l2_requires_scoped_approval_and_a_grant(self):
        self.grant("t6", operation="probe_path_alias", level="L2")
        decision, _, reason = self.pipeline.disclose(
            task_id="t6", operation="probe_path_alias", alias=ALIAS,
            fields=("excerpt",), recipient="owner", level="L2")
        self.assertEqual(("deny", "policy_requires_scoped_approved"), (decision, reason))

    def test_worker_revocation_denies_everything(self):
        self.grant("t7")
        self.workers.revoke(WORKER_ID)
        decision, _, reason = self.pipeline.disclose(
            task_id="t7", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_unavailable"), (decision, reason))

    def test_order_of_denials_is_recorded(self):
        self.pipeline.disclose(task_id="t8", operation="host_shell", alias=ALIAS,
                               fields=("exists",), recipient="owner")
        self.assertIn(("broker", "t8", "operation_not_allowed"),
                      [(row["category"], row["subject"], row["reason"]) for row in self.ledger.recent(8)])

    def test_no_raw_content_is_ever_produced(self):
        self.grant("t10", operation="read_file_alias")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t10", operation="read_file_alias", alias=ALIAS,
            fields=("exists", "size"), recipient="owner")
        self.assertEqual(("deny", "field_not_allowed_for_level"), (decision, reason))
        with open(os.path.join(self.alias_dir, "secret-note.txt"), "r", encoding="utf-8") as handle:
            private = handle.read()
        self.assertNotIn(private, repr(payload))

    def test_undeclared_alias_is_refused(self):
        self.grant("t12")
        decision, _, reason = self.pipeline.disclose(
            task_id="t12", operation="probe_path_alias", alias="elsewhere",
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_scope"), (decision, reason))

    def test_relative_alias_is_never_a_resource(self):
        self.grant("t13")
        for bad in ("../outside", "a/b", ".."):
            decision, _, reason = self.pipeline.disclose(
                task_id="t13", operation="probe_path_alias", alias=bad,
                fields=("exists",), recipient="owner")
            self.assertEqual(("deny", "resource_not_declared"), (decision, reason), bad)

    def test_empty_alias_is_a_malformed_request(self):
        self.grant("t15")
        decision, _, reason = self.pipeline.disclose(
            task_id="t15", operation="probe_path_alias", alias="",
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "malformed_request"), (decision, reason))

    def test_undeclared_path_alias_is_not_a_worker_scope(self):
        self.grant("t14")
        decision, _, reason = self.pipeline.disclose(
            task_id="t14", operation="probe_path_alias", alias=self.alias_dir,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_scope"), (decision, reason))


if __name__ == "__main__":
    unittest.main()


class PipelineOverServiceTests(unittest.TestCase):
    """The same pipeline authorizing through the authenticated loopback surface."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-pipe-svc-")
        os.chmod(self.root, stat.S_IRWXU)
        self.worker_dir = os.path.join(self.root, "workers")
        self.alias_dir = os.path.join(self.root, ALIAS)
        os.makedirs(self.worker_dir)
        os.makedirs(self.alias_dir)
        os.chmod(self.worker_dir, stat.S_IRWXU)
        os.chmod(self.alias_dir, stat.S_IRWXU)
        self.workers = WorkerRegistry(self.worker_dir)
        self.workers.create(WORKER_ID, (ALIAS,))
        self.secret = self.workers.secret_for(WORKER_ID)
        self.consent = ConsentStore(thread_safe=True)
        self.ledger = RejectionLedger()
        self.broker = Broker(worker=WorkerIdentity(WORKER_ID, scopes=(ALIAS,)),
                             scopes=ScopeAllowlist({ALIAS: self.alias_dir}),
                             consent=self.consent, consent_recipient=WORKER_ID,
                             worker_secret=self.secret, audit=self.ledger)
        self.service = BrokerService(self.broker, self.workers, WORKER_ID, self.secret)
        self.host, self.port = self.service.start()
        self.pipeline = DisclosurePipeline(worker=self.workers, consent=self.consent,
                                           aliases={ALIAS: self.alias_dir},
                                           ledger=self.ledger,
                                           service_endpoint=(self.host, self.port, WORKER_ID,
                                                             self.secret))

    def tearDown(self):
        self.service.stop()
        self.ledger.close()
        self.consent.close()
        shutil_rmtree(self.root)

    def grant(self, task_id):
        self.consent.grant(grant_id="g-{}".format(task_id), recipient=WORKER_ID,
                           task_id=task_id, field_name="probe_path_alias", alias=ALIAS,
                           level="L0", expires_at=time.time() + 60,
                           nonce="n-{}-probe_path_alias".format(task_id))

    def test_authenticated_request_releases_typed_fields(self):
        self.grant("t1")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t1", operation="probe_path_alias", alias=ALIAS,
            fields=("exists", "type"), recipient="owner")
        self.assertEqual(("release", ""), (decision, reason))
        self.assertEqual({"exists": True, "type": "dir"}, payload)

    def test_wrong_secret_is_denied_over_the_socket(self):
        self.grant("t2")
        pipeline = DisclosurePipeline(worker=self.workers, consent=self.consent,
                                      aliases={ALIAS: self.alias_dir},
                                      ledger=self.ledger,
                                      service_endpoint=(self.host, self.port, WORKER_ID, "wrong"))
        decision, payload, reason = pipeline.disclose(
            task_id="t2", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_invalid"), (decision, reason))
        self.assertEqual({}, payload)

    def test_revoked_worker_is_denied_over_the_socket(self):
        self.grant("t3")
        self.workers.revoke(WORKER_ID)
        decision, _, reason = self.pipeline.disclose(
            task_id="t3", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_invalid"), (decision, reason))

    def test_missing_grant_is_denied_over_the_socket(self):
        decision, _, reason = self.pipeline.disclose(
            task_id="t4", operation="probe_path_alias", alias=ALIAS,
            fields=("exists",), recipient="owner")
        self.assertEqual("deny", decision)
        self.assertIn(reason, ("grant_invalid", "worker_invalid"))

    def test_l2_is_refused_even_over_the_socket(self):
        self.grant("t5")
        decision, _, reason = self.pipeline.disclose(
            task_id="t5", operation="probe_path_alias", alias=ALIAS,
            fields=("excerpt",), recipient="owner", level="L2")
        self.assertEqual(("deny", "policy_requires_scoped_approved"), (decision, reason))

    def test_denials_are_recorded(self):
        self.pipeline.disclose(task_id="t6", operation="host_shell", alias=ALIAS,
                               fields=("exists",), recipient="owner")
        rows = [(row["category"], row["reason"]) for row in self.ledger.recent(8)]
        self.assertTrue(any(r[0] == "broker" for r in rows), rows)


def shutil_rmtree(path):
    import shutil

    shutil.rmtree(path, ignore_errors=True)
