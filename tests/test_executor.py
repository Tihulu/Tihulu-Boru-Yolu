"""Local worker tests: typed output only, alias-confined, receipt-bound."""
import os
import stat
import tempfile
import time
import unittest

from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity
from boru.consent import ConsentStore
from boru.errors import PolicyViolation
from boru.executor import LocalExecutor


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-exec-")
        os.chmod(self.root, stat.S_IRWXU)
        with open(os.path.join(self.root, "alpha.txt"), "w", encoding="utf-8") as handle:
            handle.write("line one\nline two\n")
        os.mkdir(os.path.join(self.root, "sub"))
        self.worker = WorkerIdentity("w1", scopes=("demo",))
        self.scopes = ScopeAllowlist({"demo": self.root})
        self.executor = LocalExecutor(self.scopes)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def authorise(self, operation, fields, nonce="n1", task="t1", grant="g1"):
        consent = ConsentStore()
        consent.grant(grant_id=grant, recipient="local-worker", task_id=task, field_name=operation,
                      level="L0", expires_at=time.time() + 60, nonce=nonce)
        broker = Broker(worker=self.worker, scopes=self.scopes, consent=consent)
        request = OperationRequest(operation=operation, resource_alias="demo", requester="owner",
                                   task_id=task, worker=self.worker, fields=fields, nonce=nonce,
                                   grant_id=grant)
        decision, receipt, reason = broker.authorize(request)
        self.assertEqual(("allow", ""), (decision, reason))
        return receipt

    def test_probe_returns_typed_fields_only(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        result = self.executor.acquire(receipt, fields=("exists", "type"), now=time.time())
        payload = result.to_dict()
        self.assertEqual({"exists": True, "type": "dir", "size": None}, payload["fields"])
        self.assertEqual("demo", payload["resource_alias"])
        self.assertNotIn(self.root, repr(payload))

    def test_list_returns_a_count_not_names(self):
        receipt = self.authorise("list_dir_alias", ("entry_count",))
        result = self.executor.acquire(receipt, fields=("exists", "entry_count"), now=time.time())
        payload = repr(result.to_dict())
        self.assertIn("entry_count", payload)
        self.assertNotIn("alpha.txt", payload)
        self.assertNotIn("sub", payload)

    def test_read_reports_metadata_only(self):
        receipt = self.authorise("read_file_alias", ("exists",))
        result = self.executor.acquire(receipt, fields=("exists", "size", "line_count"), now=time.time())
        fields = result.to_dict()["fields"]
        self.assertIn("exists", fields)
        self.assertNotIn("line one", repr(result.to_dict()))

    def test_content_is_never_produced(self):
        receipt = self.authorise("read_file_alias", ("exists",))
        for fields in (("content",), ("raw_stdout",), ("file_contents",), ("size", "content")):
            with self.assertRaises(PolicyViolation):
                self.executor.acquire(receipt, fields=fields, now=time.time())

    def test_expired_receipt_is_refused(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=receipt.expires_at + 1)

    def test_forged_receipt_is_refused(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        self.assertTrue(receipt.validate())
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_operation_must_be_executable(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        self.assertTrue(receipt.validate())
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_symlinked_alias_is_refused(self):
        link = os.path.join(self.root, "link")
        os.symlink(self.root, link)
        with self.assertRaises(PolicyViolation):
            LocalExecutor(ScopeAllowlist({"demo": link}))

    def test_missing_alias_directory_is_refused(self):
        self.scopes = ScopeAllowlist({"demo": os.path.join(self.root, "absent")})
        self.executor = LocalExecutor(self.scopes)
        receipt = self.authorise("probe_path_alias", ("exists",))
        with self.assertRaises(OSError):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_field_maps_are_bounded_and_explicit(self):
        for operation in ("probe_path_alias", "read_file_alias", "list_dir_alias", "run_synthetic_command"):
            self.assertTrue(self.executor.fields_for(operation), operation)
        self.assertEqual((), self.executor.fields_for("host_shell"))

    def test_unknown_operation_not_executable(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        self.assertTrue(receipt.validate())
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())


if __name__ == "__main__":
    unittest.main()
