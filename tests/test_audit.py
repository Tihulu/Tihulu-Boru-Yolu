"""Rejection ledger tests: append-only, bounded, sanitized, owner-confined."""
import os
import stat
import tempfile
import time
import unittest

from boru.audit import CATEGORIES, RejectionLedger
from boru.errors import ConfigurationError


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-audit-")
        os.chmod(self.root, stat.S_IRWXU)
        self.path = os.path.join(self.root, "audit.sqlite")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def ledger(self, **kwargs):
        return RejectionLedger(self.path, **kwargs)

    def test_append_and_read(self):
        with self.ledger() as ledger:
            ledger.record("policy", "task-1", "axis_mismatch")
            ledger.record("broker", "task-1", "resource_not_declared", "alias")
            self.assertEqual(2, ledger.count())
            self.assertEqual({"policy": 1, "broker": 1}, ledger.counts_by_category())
            newest = ledger.recent(1)[0]
            self.assertEqual("broker", newest["category"])
            self.assertIn("at", newest)

    def test_persistence_across_a_restart(self):
        with self.ledger() as ledger:
            ledger.record("provider", "task-9", "rate_limited")
        with self.ledger() as reopened:
            self.assertEqual(1, reopened.count())

    def test_categories_are_fixed(self):
        with self.ledger() as ledger:
            for category in CATEGORIES:
                ledger.record(category, "task-1", "generic")
            self.assertEqual(len(CATEGORIES), ledger.count())
            with self.assertRaises(ConfigurationError):
                ledger.record("mystery", "task-1", "generic")

    def test_entries_never_carry_payloads_or_paths(self):
        with self.ledger() as ledger:
            ledger.record("executor", "task-1", "content_refused", "read_file_alias")
            payload = repr(ledger.recent(4))
            self.assertNotIn(self.root, payload)
            self.assertNotIn("/home/", payload)

    def test_bounded_fields_reject_oversized_input(self):
        with self.ledger() as ledger:
            for bad in (dict(subject=""), dict(reason=""), dict(detail_kind=""),
                        dict(subject="x" * 200), dict(reason="x" * 200),
                        dict(detail_kind="x" * 200), dict(at=-1), dict(at="yesterday")):
                with self.assertRaises(ConfigurationError):
                    ledger.record("policy", bad.get("subject", "t1"), bad.get("reason", "r1"),
                                  bad.get("detail_kind", "none"), at=bad.get("at"))

    def test_limit_and_cap_bounds(self):
        for bad in (0, True, "10", 999999):
            with self.assertRaises(ConfigurationError):
                RejectionLedger(self.path, cap=bad)
        with RejectionLedger(self.path) as ledger:
            for bad in (0, True, "5", 99999):
                with self.assertRaises(ConfigurationError):
                    ledger.recent(bad)

    def test_retention_prunes_the_oldest_rows_only(self):
        with RejectionLedger(self.path, cap=32) as ledger:
            for index in range(50):
                ledger.record("budget", "task-{}".format(index), "ceiling", "task")
            self.assertEqual(32, ledger.count())
            subjects = [row["subject"] for row in ledger.recent(64)]
            self.assertIn("task-49", subjects)
            self.assertNotIn("task-0", subjects)

    def test_bad_paths_rejected(self):
        for bad in ("", "   ", 5, "x" * 5000):
            with self.assertRaises(ConfigurationError):
                RejectionLedger(bad)
        link = os.path.join(self.root, "link")
        os.symlink(self.path, link)
        with self.assertRaises(ConfigurationError):
            RejectionLedger(link)

    def test_group_writable_directory_rejected(self):
        os.chmod(self.root, stat.S_IRWXU | stat.S_IWGRP)
        try:
            with self.assertRaises(ConfigurationError):
                RejectionLedger(self.path)
        finally:
            os.chmod(self.root, stat.S_IRWXU)

    def test_file_permissions_are_owner_only(self):
        with RejectionLedger(self.path) as ledger:
            pass
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(0, mode & (stat.S_IRWXG | stat.S_IRWXO))

    def test_in_memory_sink_works(self):
        with RejectionLedger() as ledger:
            ledger.record("review", "task-1", "owner_review_failed", "review")
            self.assertEqual(1, ledger.count())

    def test_unknown_schema_version_rejected(self):
        import sqlite3

        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA user_version = 5")
        connection.commit()
        connection.close()
        with self.assertRaises(ConfigurationError):
            RejectionLedger(self.path)


if __name__ == "__main__":
    unittest.main()
