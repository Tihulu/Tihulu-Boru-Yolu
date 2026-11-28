"""Worker identity registry tests: bounded lifetimes, revocation, confinement."""
import os
import stat
import tempfile
import time
import unittest

from boru.errors import ConfigurationError
from boru.workers import DEFAULT_TTL_SECONDS, WorkerRecord, WorkerRegistry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-workers-")
        os.chmod(self.root, stat.S_IRWXU)
        self.dir = os.path.join(self.root, "workers")
        os.makedirs(self.dir)
        os.chmod(self.dir, stat.S_IRWXU)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_create_validate_revoke(self):
        with WorkerRegistry(self.dir) as registry:
            record = registry.create("w1", ("demo",))
            self.assertEqual([], record.validate())
            self.assertEqual(("demo",), record.scopes)
            self.assertGreater(record.expires_at, record.issued_at)
            self.assertTrue(registry.valid("w1", registry.secret_for("w1")))
            self.assertFalse(registry.valid("w1", "not-the-secret"))
            registry.revoke("w1")
            self.assertFalse(registry.valid("w1", registry.secret_for("w1")))
            self.assertTrue(registry.get("w1").revoked)

    def test_secrets_are_256_bit_and_never_returned(self):
        with WorkerRegistry(self.dir) as registry:
            registry.create("w2", ("demo",))
            self.assertEqual(64, len(registry.secret_for("w2")))
            with open(os.path.join(self.dir, "worker-w2.json"), "r", encoding="utf-8") as handle:
                stored = handle.read()
            self.assertIn("secret", stored)
            self.assertEqual(0, stat.S_IMODE(os.stat(os.path.join(self.dir, "worker-w2.json")).st_mode)
                             & (stat.S_IRWXG | stat.S_IRWXO))

    def test_persistence_across_restart(self):
        with WorkerRegistry(self.dir) as registry:
            registry.create("w3", ("demo",))
        with WorkerRegistry(self.dir) as reopened:
            self.assertEqual(["w3"], [w.worker_id for w in reopened.all()])
            self.assertTrue(reopened.valid("w3", reopened.secret_for("w3")))

    def test_expiry_enforced(self):
        with WorkerRegistry(self.dir, ttl_seconds=1.0) as registry:
            registry.create("w4", ("demo",), now=time.time())
            later = time.time() + 5
            self.assertFalse(registry.valid("w4", registry.secret_for("w4"), now=later))

    def test_bounded_registry(self):
        with WorkerRegistry(self.dir, ttl_seconds=3600.0) as registry:
            for index in range(8):
                registry.create("w{}".format(index), ("scope-{}".format(index),))
            with self.assertRaises(ConfigurationError):
                registry.create("extra", ("scope-8",))
            with self.assertRaises(ConfigurationError):
                registry.create("w0", ("scope-8",))

    def test_bad_inputs_rejected(self):
        with WorkerRegistry(self.dir) as registry:
            for bad in (("", ("demo",)), ("x" * 200, ("demo",)), ("w", ()), ("w", ("a", "a")),
                        ("w", ("x" * 200,)), ("w", ("",))):
                with self.assertRaises(ConfigurationError):
                    registry.create(*bad)
            with self.assertRaises(ConfigurationError):
                registry.revoke("missing")
            with self.assertRaises(ConfigurationError):
                registry.delete("missing")
            # an unknown but well-formed worker id is simply not valid
            self.assertFalse(registry.valid("missing", "x"))
            with self.assertRaises(ConfigurationError):
                registry.get("")

    def test_ttl_bounds(self):
        for bad in (0, True, "900", 999999):
            with self.assertRaises(ConfigurationError):
                WorkerRegistry(self.dir, ttl_seconds=bad)
        self.assertEqual(900.0, DEFAULT_TTL_SECONDS)

    def test_directory_must_be_safe(self):
        for bad in ("", "   ", 5, "x" * 5000, os.path.join(self.root, "absent"),
                    os.path.join(self.root, "link")):
            if not isinstance(bad, str) or not bad:
                continue
            if "link" in str(bad):
                link = os.path.join(self.root, "link")
                os.symlink(self.dir, link)
            with self.assertRaises(ConfigurationError):
                WorkerRegistry(bad)
            if os.path.islink(str(bad)):
                os.unlink(str(bad))

    def test_group_writable_directory_rejected(self):
        os.chmod(self.dir, stat.S_IRWXU | stat.S_IWGRP)
        try:
            with self.assertRaises(ConfigurationError):
                WorkerRegistry(self.dir)
        finally:
            os.chmod(self.dir, stat.S_IRWXU)

    def test_bad_worker_file_rejected(self):
        with open(os.path.join(self.dir, "worker-bad.json"), "w", encoding="utf-8") as handle:
            import json

            json.dump({"worker_id": "bad", "scopes": ["demo"], "issued_at": 1.0,
                       "expires_at": 2.0, "secret": "short"}, handle)
        with self.assertRaises(ConfigurationError):
            WorkerRegistry(self.dir)

    def test_symlinked_worker_file_rejected(self):
        with WorkerRegistry(self.dir) as registry:
            registry.create("w5", ("demo",))
        target = os.path.join(self.dir, "worker-link.json")
        os.symlink(os.path.join(self.dir, "worker-w5.json"), target)
        try:
            with self.assertRaises(ConfigurationError):
                WorkerRegistry(self.dir)
        finally:
            os.unlink(target)

    def test_bad_record_validation(self):
        self.assertTrue(WorkerRecord(worker_id="", scopes=("demo",), issued_at=1.0,
                                     expires_at=2.0).validate())
        self.assertTrue(WorkerRecord(worker_id="w", scopes=("a", "a"), issued_at=1.0,
                                     expires_at=2.0).validate())
        self.assertTrue(WorkerRecord(worker_id="w", scopes=("demo",), issued_at=1.0,
                                     expires_at=1.0).validate())
        self.assertEqual([], WorkerRecord(worker_id="w", scopes=("demo",), issued_at=1.0,
                                         expires_at=2.0).validate())
