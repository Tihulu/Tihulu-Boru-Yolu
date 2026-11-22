"""Local state store tests: durability, containment and idempotency."""
import json
import os
import shutil
import stat
import sqlite3
import tempfile
import unittest

from boru.config import ProviderConfig, CoreConfig
from boru.core import BoruCore
from boru.errors import ConfigurationError, DuplicateTask, StoreError
from boru.state import TaskState
from boru.store import TaskStore
from boru.types import TaskEnvelope

STAMP = "2026-01-01T00:00:00Z"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-test-")
        os.chmod(self.root, stat.S_IRWXU)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store(self):
        return TaskStore(self.root)

    def envelope(self, task_id="t1"):
        return TaskEnvelope(task_id=task_id, goal="g")

    def test_memory_default(self):
        store = TaskStore()
        self.assertIsNone(store._path)
        store.close()

    def test_submit_is_idempotent(self):
        with self.store() as store:
            created, row = store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            self.assertTrue(created)
            again, row = store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            self.assertFalse(again)
            with self.assertRaises(DuplicateTask):
                store.submit("t1", "k2", TaskEnvelope(task_id="t1", goal="different"), "CREATED", STAMP)

    def test_capacity_limit(self):
        with TaskStore(self.root, max_records=1) as store:
            store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            with self.assertRaises(StoreError):
                store.ensure_capacity()

    def test_compare_and_set_transition(self):
        with self.store() as store:
            store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            store.transition("t1", "CREATED", "QUEUED", "planned", STAMP)
            with self.assertRaises(StoreError):
                store.transition("t1", "CREATED", "RUNNING", "again", STAMP)
            with self.assertRaises(StoreError):
                store.transition("missing", "CREATED", "RUNNING", "again", STAMP)

    def test_persistence_across_restart(self):
        with self.store() as store:
            store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            store.transition("t1", "CREATED", "QUEUED", "planned", STAMP)
        with self.store() as store2:
            self.assertEqual("QUEUED", store2.get("t1")["state"])
            self.assertEqual(TaskState.QUEUED.value, store2.queued()[0]["state"])
            self.assertIsInstance(store2.envelope("t1"), dict)

    def test_state_file_permissions(self):
        with self.store() as store:
            pass
        path = os.path.join(self.root, "boru-state.sqlite")
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(0, stat.S_IMODE(os.stat(path).st_mode) & (stat.S_IRWXG | stat.S_IRWXO))

    def test_group_writable_directory_rejected(self):
        os.chmod(self.root, stat.S_IRWXU | stat.S_IWGRP)
        try:
            os.chmod(self.root, 0o770)
            with self.assertRaises(ConfigurationError):
                TaskStore(self.root)
        finally:
            os.chmod(self.root, stat.S_IRWXU)

    def test_missing_directory_rejected(self):
        with self.assertRaises(ConfigurationError):
            TaskStore(os.path.join(self.root, "absent"))

    def test_symlinked_state_directory_rejected(self):
        link = os.path.join(self.root, "link")
        if not os.path.exists(link):
            os.symlink(self.root, link)
        with self.assertRaises(ConfigurationError):
            TaskStore(link)

    def test_schema_version_and_corruption_rejected(self):
        path = os.path.join(self.root, "boru-state.sqlite")
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
        connection.close()
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        with self.assertRaises(StoreError):
            TaskStore(self.root)

    def test_missing_table_rejected(self):
        with self.store() as store:
            pass
        connection = sqlite3.connect(os.path.join(self.root, "boru-state.sqlite"))
        connection.execute("DROP TABLE attempts")
        connection.commit()
        connection.close()
        with self.assertRaises(StoreError):
            TaskStore(self.root)

    def test_bad_max_records(self):
        for bad in (0, True, "5"):
            with self.assertRaises(ConfigurationError):
                TaskStore(self.root, max_records=bad)

    def test_bounded_result_payload(self):
        with self.store() as store:
            store.submit("t1", "k1", self.envelope("t1"), "CREATED", STAMP)
            with self.assertRaises(StoreError):
                store.save_result("t1", "a1", {"text": "x" * 300000})


class PersistenceTests(unittest.TestCase):
    """End-to-end recoverable task state with a durable store."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-test-")
        os.chmod(self.root, stat.S_IRWXU)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def core(self):
        config = CoreConfig(providers=(ProviderConfig(kind="mock"),))
        return BoruCore(config, store=TaskStore(self.root))

    def test_interrupted_running_task_recovers_to_hold(self):
        core = self.core()
        core.submit(TaskEnvelope(task_id="t1", goal="g"))
        store = core.store
        store.transition("t1", "QUEUED", "RUNNING", "dispatch_started", STAMP)
        core.close()
        reopened = self.core()
        self.assertEqual(["t1"], reopened.recover())
        self.assertEqual("HOLD", reopened.status("t1")["state"])
        reopened.close()

    def test_review_state_survives_restart_without_auto_done(self):
        core = self.core()
        core.submit(TaskEnvelope(task_id="t1", goal="g"))
        summary = core.dispatch_next()
        self.assertEqual("REVIEW", summary["state"])
        core.close()
        reopened = self.core()
        row = reopened.status("t1")
        self.assertEqual("REVIEW", row["state"])
        self.assertEqual("simulated", row["evidence_class"])
        self.assertEqual("HOLD", row["live_acceptance"])
        reopened.close()

    def test_review_persists_done_and_evidence_class(self):
        core = self.core()
        core.submit(TaskEnvelope(task_id="t1", goal="g"))
        core.dispatch_next()
        self.assertEqual("DONE", core.review("t1", accept=True))
        core.close()
        reopened = self.core()
        row = reopened.status("t1")
        self.assertEqual("DONE", row["state"])
        self.assertEqual("simulated", row["evidence_class"])
        self.assertEqual("HOLD", row["live_acceptance"])
        reopened.close()

    def test_review_cannot_promote_evidence_class(self):
        core = self.core()
        core.submit(TaskEnvelope(task_id="t1", goal="g"))
        core.dispatch_next()
        core.review("t1", accept=True)
        row = core.status("t1")
        self.assertEqual("simulated", row["evidence_class"])
        self.assertNotEqual("direct", row["evidence_class"])
        core.close()

    def test_review_rejects_non_review_state(self):
        from boru.errors import VerificationError

        core = self.core()
        core.submit(TaskEnvelope(task_id="t1", goal="g"))
        with self.assertRaises(VerificationError):
            core.review("t1", accept=True)
        core.close()


class ResultShapeTests(unittest.TestCase):
    """A stored attempt record must be a JSON object, and reading it never crashes."""

    def test_a_non_object_result_is_refused(self):
        from boru.errors import StoreError

        store = TaskStore()
        try:
            for bad in (["list"], "text", 5, None):
                with self.assertRaises(StoreError):
                    store.save_result("t", "a", bad)
        finally:
            store.close()

    def test_result_text_tolerates_a_hostile_row(self):
        import json

        from boru.core import BoruCore
        from boru.config import CoreConfig, ProviderConfig
        from boru.types import TaskEnvelope

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        try:
            envelope = TaskEnvelope(task_id="t1", goal="hello")
            engine.submit(envelope)
            # a row written by another writer (corruption, or an older build)
            # must read as "no text", never as a crash
            engine.store._db.execute(
                "INSERT OR REPLACE INTO attempts(task_id, attempt_id, result) VALUES(?,?,?)",
                ("t1", "a", json.dumps(["not", "an", "object"], ensure_ascii=True)))
            self.assertIsNone(engine.result_text("t1"))
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
