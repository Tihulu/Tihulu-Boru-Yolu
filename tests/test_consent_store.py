"""Persistent consent store tests: revocation, expiry and replay survive restart."""
import os
import stat
import tempfile
import time
import unittest

from boru.consent import MAX_NONCES, ConsentStore
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
            store.grant(grant_id="g1", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 60, nonce="n1")
            self.assertTrue(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", alias="demo", nonce="n1"))
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="demo", nonce="n1"))

    def test_grants_survive_restart_and_revocation_sticks(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g1", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 600, nonce="n1")
        with ConsentStore(self.path) as store:
            self.assertTrue(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", alias="demo", nonce="n1"))
            store.revoke("g1")
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="demo", nonce="n1"))
        with ConsentStore(self.path) as store:
            self.assertFalse(store.check(grant_id="g1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="demo", nonce="n1"))

    def test_expiry_is_enforced_after_restart(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g2", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 1, nonce="n2")
        with ConsentStore(self.path) as store:
            self.assertFalse(store.check(grant_id="g1" "g2".replace("g1", ""), recipient="cloud",
                                         task_id="t1", field_name="excerpt", alias="demo", nonce="n2",
                                         now=time.time() + 10))

    def test_binding_is_recipient_task_and_field(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g3", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 60, nonce="n3")
            self.assertFalse(store.check(grant_id="g3", recipient="other", task_id="t1",
                                         field_name="excerpt", alias="demo", nonce="n3"))
            self.assertFalse(store.check(grant_id="g3", recipient="cloud", task_id="t2",
                                         field_name="excerpt", alias="demo", nonce="n3"))
            self.assertFalse(store.check(grant_id="g3", recipient="cloud", task_id="t1",
                                         field_name="status", alias="demo", nonce="n3"))

    def test_active_listing_excludes_expired_and_revoked(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="g4", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 60, nonce="n4")
            store.grant(grant_id="g5", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 1, nonce="n5")
            store.grant(grant_id="g6", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
                       level="L2", expires_at=time.time() + 60, nonce="n6")
            store.revoke("g6")
            self.assertEqual(["g4", "g5"], sorted(row["grant_id"] for row in store.active()))
            self.assertEqual(["g4"], sorted(row["grant_id"] for row in store.active(now=time.time() + 10)))

    def test_bad_grants_rejected(self):
        with ConsentStore(self.path) as store:
            base = dict(grant_id="g", recipient="cloud", task_id="t1", field_name="excerpt", alias="demo",
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
                       alias="demo", level="L2", expires_at=time.time() + 60, nonce="n")
            self.assertTrue(store.check(grant_id="m", recipient="cloud", task_id="t1",
                                        field_name="excerpt", alias="demo", nonce="n"))

    def test_unknown_schema_version_rejected(self):
        import sqlite3

        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
        connection.close()
        with self.assertRaises(Exception):
            ConsentStore(self.path)


    def test_grant_is_bound_to_its_alias_and_level(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="a1", recipient="cloud", task_id="t1", field_name="excerpt",
                        alias="demo", level="L0", expires_at=time.time() + 60, nonce="na1")
            self.assertTrue(store.check(grant_id="a1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", alias="demo", nonce="na1"))
            # a grant for one resource never serves another
            self.assertFalse(store.check(grant_id="a1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="other", nonce="na2"))
            # a weaker grant never authorizes a wider disclosure level
            self.assertFalse(store.check(grant_id="a1", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="demo", level="L2",
                                         nonce="na3"))

    def test_grant_id_is_immutable_once_issued(self):
        with ConsentStore(self.path) as store:
            store.grant(grant_id="a2", recipient="cloud", task_id="t1", field_name="excerpt",
                        alias="demo", level="L2", expires_at=time.time() + 60, nonce="na4")
            store.revoke("a2")
            # a revocation cannot be reset by re-issuing the same grant id
            with self.assertRaises(ConfigurationError):
                store.grant(grant_id="a2", recipient="cloud", task_id="t1", field_name="excerpt",
                            alias="demo", level="L2", expires_at=time.time() + 60, nonce="na5")

    def test_an_alias_is_a_bounded_binding_not_a_judged_path(self):
        # path policy belongs to the broker/allowlist: this store only binds a
        # bounded, trimmed token with no control characters
        with ConsentStore(self.path) as store:
            for bad in ("", " ", "with space", "x" * 1025):
                with self.assertRaises(ConfigurationError):
                    store.grant(grant_id="p", recipient="cloud", task_id="t1",
                                field_name="excerpt", alias=bad, level="L0",
                                expires_at=time.time() + 60, nonce="np")
            # a declared absolute path is a legal binding token here
            store.grant(grant_id="p1", recipient="cloud", task_id="t1",
                        field_name="excerpt", alias="/home/EXAMPLE/data", level="L0",
                        expires_at=time.time() + 60, nonce="np1")
            self.assertTrue(store.check(grant_id="p1", recipient="cloud", task_id="t1",
                                        field_name="excerpt", alias="/home/EXAMPLE/data",
                                        nonce="np1"))

    def test_used_nonces_fail_closed_rather_than_evict_a_live_one(self):
        # A used nonce outlives the grant that carried it: past the bound the
        # store refuses new work instead of evicting a nonce whose grant is
        # still live, so a live grant is never replayable.
        with ConsentStore(self.path) as store:
            for index in range(MAX_NONCES + 32):
                store.grant(grant_id="b{}".format(index), recipient="cloud",
                            task_id="t1", field_name="excerpt", alias="demo", level="L0",
                            expires_at=time.time() + 60, nonce="nb{}".format(index))
                allowed = store.check(grant_id="b{}".format(index), recipient="cloud",
                                      task_id="t1", field_name="excerpt", alias="demo",
                                      nonce="nb{}".format(index))
                if index < MAX_NONCES:
                    self.assertTrue(allowed, index)
                else:
                    self.assertFalse(allowed, index)
            stored = int(store._db.execute("SELECT COUNT(*) FROM used_nonces").fetchone()[0])
            self.assertLessEqual(stored, MAX_NONCES)
            # and the first grant is still replay-protected: its nonce was not
            # evicted to make room for the refused ones
            self.assertFalse(store.check(grant_id="b0", recipient="cloud", task_id="t1",
                                         field_name="excerpt", alias="demo", nonce="nb0"))


if __name__ == "__main__":
    unittest.main()
