"""Persistent consent store tests: revocation, expiry and replay survive restart."""
import os
import stat
import tempfile
import time
import unittest

from boru.consent import ConsentStore
from boru.errors import ConfigurationError


class PersistentConsentTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-consent-")
        os.chmod(self.root, stat.S_IRWXU)
        self.path = os.path.join(self.root, "consents.sqlite")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_grant_check_and_replay(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g1", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n1")
            self.assertTrue(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", nonce="n1"))
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", nonce="n1"))

    def test_grants_survive_restart_and_revocation_sticks(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g1", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 600, nonce="n1")
        with ConsentStore(self.path) as store:
            self.assertTrue(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", nonce="n1"))
            store.revoke("g1")
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", nonce="n1"))
        with ConsentStore(self.path) as store:
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", nonce="n1"))

    def test_expiry_is_enforced_after_restart(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g2", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 1, nonce="n2")
        with ConsentStore(self.path) as store:
            self.assertFalse(store.check(grant_id="g1" "g2".replace("g1", ""), recipient="cloud",
                                         task_id="t1", field_name="excerpt", nonce="n2",
                                         now=time.time() + 10))

    def test_binding_is_recipient_task_and_field(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g3", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n3")
            self.assertFalse(store.check(grant_id="g3", recipient="other", task_id="t1",
                                         field_name="excerpt", nonce="n3"))
            self.assertFalse(store.check(grant_id="g3", recipient="cloud", task_id="t2",
                                         field_name="excerpt", nonce="n3"))
            self.assertFalse(store.check(grant_id="g3", recipient="cloud", task_id="t1",
                                         field_name="status", nonce="n3"))

    def test_active_listing_excludes_expired_and_revoked(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g4", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n4")
            store.grant(grant_id="g5", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 1, nonce="n5")
            store.grant(grant_id="g6", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n6")
            store.revoke("g6")
            self.assertEqual(["g4", "g5"], sorted(row["grant_id"] for row in store.active()))
            self.assertEqual(["g4"], sorted(row["grant_id"] for row in store.active(now=time.time() + 10)))

    def test_bad_grants_rejected(self):
        with ConsentStore(self.path) as store:
            base = dict(grant_id="g", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n")
            for bad in (dict(grant_id=""), dict(nonce=""), dict(expires_at="soon"),
                        dict(expires_at=time.time() - 60), dict(level="L"), dict(field_name="")):
                with self.assertRaises((ValueError, TypeError)):
                    store.grant(**dict(base, **bad))

    def test_bad_paths_rejected(self):
        for bad in ("", "   ", 5, "x" * 5000):
            with self.assertRaises(ConfigurationError):
                ConsentStore(bad)
        link = os.path.join(self.root, "link")
        os.symlink(self.path, link)
        with self.assertRaises(ConfigurationError):
            ConsentStore(link)

    def test_group_writable_directory_rejected(self):
        os.chmod(self.root, stat.S_IRWXU | stat.S_IWGRP)
        try:
            with self.assertRaises(ConfigurationError):
                ConsentStore(os.path.join(self.root, "consents.sqlite"))
        finally:
            os.chmod(self.root, stat.S_IRWXU)

    def test_file_permissions_are_owner_only(self):
        with ConsentStore(self.path) as store:
            pass
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(0, mode & (stat.S_IRWXG | stat.S_IRWXO))

    def test_in_memory_store_works(self):
        with ConsentStore() as store:
            store.grant(grant_id="m", recipient="cloud", task_id="t1", field_name="excerpt",
                       level="L2", expires_at=time.time() + 60, nonce="n")
            self.assertTrue(store.check(grant_id="m", recipient="cloud", task_id="t1",
                                        field_name="excerpt", nonce="n"))

    def test_unknown_schema_version_rejected(self):
        import sqlite3

        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
        connection.close()
        with self.assertRaises(Exception):
            ConsentStore(self.path)


if __name__ == "__main__":
    unittest.main()
