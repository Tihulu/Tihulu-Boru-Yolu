"""End-to-end local disclosure pipeline tests (P5): every denial path holds."""
import os
import stat
import tempfile
import time
import unittest

from boru.audit import RejectionLedger
from boru.consent import ConsentStore
from boru.pipeline import WORKER_ID, DisclosurePipeline
from boru.workers import WorkerRegistry


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-pipeline-")
        os.chmod(self.root, stat.S_IRWXU)
        self.worker_dir = os.path.join(self.root, "workers")
        self.alias = os.path.join(self.root, "demo-project")
        os.makedirs(self.worker_dir)
        os.makedirs(self.alias)
        os.chmod(self.worker_dir, stat.S_IRWXU)
        os.chmod(self.alias, stat.S_IRWXU)
        with open(os.path.join(self.alias, "secret-note.txt"), "w", encoding="utf-8") as handle:
            handle.write("private content\n")
        self.workers = WorkerRegistry(self.worker_dir)
        self.workers.create(WORKER_ID, (self.alias,))
        self.consent = ConsentStore()
        self.ledger = RejectionLedger()
        self.pipeline = DisclosurePipeline(worker=self.workers, consent=self.consent,
                                           ledger=self.ledger)

    def tearDown(self):
        import shutil

        self.workers.delete(WORKER_ID)
        shutil.rmtree(self.root, ignore_errors=True)

    def grant(self, task_id, operation="probe_path_alias", level="L0", ttl=60):
        self.consent.grant(grant_id="g-{}".format(task_id), recipient=WORKER_ID, task_id=task_id,
                           field_name=operation, level=level,
                           expires_at=time.time() + ttl,
                           nonce="n-{}-{}".format(task_id, operation))

    def test_l0_release_carries_typed_fields_only(self):
        self.grant("t1")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t1", operation="probe_path_alias", alias=self.alias,
            fields=("exists", "type"), recipient="owner")
        self.assertEqual(("release", ""), (decision, reason))
        self.assertEqual({"exists": True, "type": "dir"}, payload)
        self.assertNotIn("secret-note", repr(payload))
        self.assertNotIn(self.root, repr(payload))

    def test_order_returns_a_count_not_names(self):
        self.grant("t2", operation="list_dir_alias")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t2", operation="list_dir_alias", alias=self.alias,
            fields=("exists", "entry_count"), recipient="owner")
        self.assertEqual("release", decision)
        self.assertIn("entry_count", payload)
        self.assertNotIn("secret-note.txt", repr(payload))

    def test_missing_grant_denies(self):
        decision, payload, reason = self.pipeline.disclose(
            task_id="t9", operation="probe_path_alias", alias=self.alias,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))
        self.assertEqual({}, payload)
        self.assertIn(("broker", "t9", "grant_invalid"),
                      [(row["category"], row["subject"], row["reason"]) for row in self.ledger.recent(8)])

    def test_expired_grant_denies(self):
        self.grant("t3", ttl=0.2)
        later = time.time() + 5
        decision, _, reason = self.pipeline.disclose(
            task_id="t3", operation="probe_path_alias", alias=self.alias,
            fields=("exists",), recipient="owner", now=later)
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_operation_not_granted_denies(self):
        self.grant("t4", operation="probe_path_alias")
        decision, _, reason = self.pipeline.disclose(
            task_id="t4", operation="read_file_alias", alias=self.alias,
            fields=("exists",), recipient="owner")
        # the operation is allowed in principle, but the consent grant names a
        # different operation, so the broker denies it
        self.assertEqual(("deny", "grant_invalid"), (decision, reason))

    def test_l1_requires_a_wider_declaration(self):
        self.grant("t5")
        decision, _, reason = self.pipeline.disclose(
            task_id="t5", operation="probe_path_alias", alias=self.alias,
            fields=("size",), recipient="owner")
        self.assertEqual(("deny", "field_not_allowed_for_level"), (decision, reason))

    def test_l2_requires_scoped_approval_and_a_grant(self):
        self.grant("t6", operation="probe_path_alias", level="L2")
        decision, _, reason = self.pipeline.disclose(
            task_id="t6", operation="probe_path_alias", alias=self.alias,
            fields=("excerpt",), recipient="owner", level="L2")
        self.assertEqual(("deny", "policy_requires_scoped_approved"), (decision, reason))

    def test_worker_revocation_denies_everything(self):
        self.grant("t7")
        self.workers.revoke(WORKER_ID)
        decision, _, reason = self.pipeline.disclose(
            task_id="t7", operation="probe_path_alias", alias=self.alias,
            fields=("exists",), recipient="owner")
        self.assertEqual(("deny", "worker_unavailable"), (decision, reason))

    def test_order_of_denials_is_recorded(self):
        self.pipeline.disclose(task_id="t8", operation="host_shell", alias=self.alias,
                              fields=("exists",), recipient="owner")
        self.assertIn(("broker", "t8", "operation_not_allowed"),
                      [(row["category"], row["subject"], row["reason"]) for row in self.ledger.recent(8)])

    def test_no_raw_content_is_ever_produced(self):
        self.grant("t10", operation="read_file_alias")
        decision, payload, reason = self.pipeline.disclose(
            task_id="t10", operation="read_file_alias", alias=self.alias,
            fields=("exists", "size"), recipient="owner")
        self.assertEqual(("deny", "field_not_allowed_for_level"), (decision, reason))
        with open(os.path.join(self.alias, "secret-note.txt"), "r", encoding="utf-8") as handle:
            private = handle.read()
        self.assertNotIn(private, repr(payload))


if __name__ == "__main__":
    unittest.main()
