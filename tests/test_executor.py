"""Local worker tests: typed output only, alias-confined, receipt-bound."""
import dataclasses
import os
import stat
import tempfile
import time
import unittest

from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity
from boru.consent import ConsentStore
from boru.errors import PolicyViolation
from boru.executor import LocalExecutor

#: "line one\nline two\n" is exactly 18 bytes with two newlines.
ALPHA_SIZE = 18
ALPHA_LINES = 2


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-exec-")
        os.chmod(self.root, stat.S_IRWXU)
        with open(os.path.join(self.root, "alpha.txt"), "w", encoding="utf-8") as handle:
            handle.write("line one\nline two\n")
        os.mkdir(os.path.join(self.root, "sub"))
        self.worker = WorkerIdentity("w1", scopes=("demo",))
        self.scopes = ScopeAllowlist({"demo": self.root})
        # An explicit test key stands in for the worker-secret derived key: a
        # broker and a worker that share it verify the same receipts.
        self.key = bytes(range(32))
        self.executor = LocalExecutor(self.scopes, authorization_key=self.key)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def authorise(self, operation, fields, nonce="n1", task="t1", grant="g1", target=None):
        consent = ConsentStore()
        consent.grant(grant_id=grant, recipient="w1", task_id=task, field_name=operation,
                      alias="demo", level="L0", expires_at=time.time() + 60, nonce=nonce)
        broker = Broker(worker=self.worker, scopes=self.scopes, consent=consent,
                        authorization_key=self.key)
        request = OperationRequest(operation=operation, resource_alias="demo", requester="owner",
                                   task_id=task, worker=self.worker, fields=fields, nonce=nonce,
                                   grant_id=grant, target=target)
        decision, receipt, reason = broker.authorize(request, requested_fields=fields)
        self.assertEqual(("allow", ""), (decision, reason))
        return receipt

    def test_probe_returns_typed_fields_only(self):
        receipt = self.authorise("probe_path_alias", ("exists", "type", "size"))
        result = self.executor.acquire(receipt, fields=("exists", "type", "size"), now=time.time())
        payload = result.to_dict()
        self.assertEqual({"exists": True, "type": "dir", "size": None}, payload["fields"])
        self.assertEqual("demo", payload["resource_alias"])
        self.assertNotIn(self.root, repr(payload))

    def test_list_returns_a_count_not_names(self):
        receipt = self.authorise("list_dir_alias", ("entry_count",))
        result = self.executor.acquire(receipt, fields=("entry_count",), now=time.time())
        payload = repr(result.to_dict())
        self.assertIn("entry_count", payload)
        self.assertNotIn("alpha.txt", payload)
        self.assertNotIn("sub", payload)

    def test_probe_reports_a_real_target_entry(self):
        receipt = self.authorise("probe_path_alias", ("exists", "type", "size"), target="alpha.txt")
        result = self.executor.acquire(receipt, fields=("exists", "type", "size"),
                                       now=time.time())
        self.assertEqual({"exists": True, "type": "file", "size": ALPHA_SIZE},
                         result.to_dict()["fields"])

    def test_probe_of_an_absent_entry_reports_not_found(self):
        receipt = self.authorise("probe_path_alias", ("exists", "type", "size"), target="absent.txt")
        result = self.executor.acquire(receipt, fields=("exists", "type", "size"), now=time.time())
        self.assertEqual({"exists": False, "type": None, "size": None},
                         result.to_dict()["fields"])

    def test_read_reports_real_metadata_only(self):
        receipt = self.authorise("read_file_alias", ("exists", "size", "line_count"), target="alpha.txt")
        result = self.executor.acquire(
            receipt, fields=("exists", "size", "line_count"), now=time.time())
        fields = result.to_dict()["fields"]
        self.assertEqual({"exists": True, "size": ALPHA_SIZE, "line_count": ALPHA_LINES}, fields)
        self.assertNotIn("line one", repr(result.to_dict()))

    def test_read_without_a_target_is_refused(self):
        receipt = self.authorise("read_file_alias", ("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_read_rejects_a_directory_target(self):
        receipt = self.authorise("read_file_alias", ("exists",), target="sub")
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(
                receipt, fields=("exists", "size"), now=time.time())

    def test_symlinked_target_is_not_followed(self):
        os.symlink(os.path.join(self.root, "alpha.txt"), os.path.join(self.root, "link.txt"))
        receipt = self.authorise("probe_path_alias", ("exists", "type"), target="link.txt")
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(
                receipt, fields=("exists",), now=time.time())

    def test_traversal_target_never_escapes_the_alias(self):
        # a signed receipt exists only for single-segment names
        for bad in ("../outside", "sub/alpha.txt", "/etc/passwd", "..", ""):
            with self.assertRaises(AssertionError):
                self.authorise("probe_path_alias", ("exists",), target=bad)

    def test_worker_refuses_fields_beyond_the_receipt(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists", "type"), now=time.time())

    def test_content_is_never_produced(self):
        receipt = self.authorise("read_file_alias", ("exists",), target="alpha.txt")
        for fields in (("content",), ("raw_stdout",), ("file_contents",), ("size", "content")):
            with self.assertRaises(PolicyViolation):
                self.executor.acquire(receipt, fields=fields, now=time.time())

    def test_expired_receipt_is_refused(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(
                receipt, fields=("exists",), now=receipt.expires_at + 1)

    def test_forged_receipt_is_refused(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        with self.assertRaises(PolicyViolation):
            receipt.verify(self.key, now=time.time(), requested_fields=("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(
                receipt, fields=("exists",), now=time.time())

    def test_a_borrowed_receipt_fails_under_a_foreign_key(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        stranger = LocalExecutor(self.scopes, authorization_key=bytes(range(31, -1, -1)))
        with self.assertRaises(PolicyViolation):
            stranger.acquire(receipt, fields=("exists",), now=time.time())

    def test_a_swapped_target_invalidates_the_receipt(self):
        receipt = self.authorise("probe_path_alias", ("exists",), target="alpha.txt")
        swapped = dataclasses.replace(receipt, target="sub")
        with self.assertRaises(PolicyViolation):
            swapped.verify(self.key, now=time.time(), requested_fields=("exists",))

    def test_operation_must_be_executable(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        with self.assertRaises(PolicyViolation):
            receipt.verify(self.key, now=time.time(), requested_fields=("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_unknown_operation_not_executable(self):
        receipt = self.authorise("probe_path_alias", ("exists",))
        object.__setattr__(receipt, "operation", "host_shell")
        with self.assertRaises(PolicyViolation):
            receipt.verify(self.key, now=time.time(), requested_fields=("exists",))
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_symlinked_alias_is_refused(self):
        link = os.path.join(self.root, "link")
        os.symlink(self.root, link)
        with self.assertRaises(PolicyViolation):
            LocalExecutor(ScopeAllowlist({"demo": link}), authorization_key=self.key)

    def test_missing_alias_directory_is_refused(self):
        self.scopes = ScopeAllowlist({"demo": os.path.join(self.root, "absent")})
        self.executor = LocalExecutor(self.scopes, authorization_key=self.key)
        receipt = self.authorise("probe_path_alias", ("exists",))
        with self.assertRaises(OSError):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_a_blocking_special_file_never_hangs_the_worker(self):
        # a FIFO inside the alias must answer immediately, not block the worker
        os.mkfifo(os.path.join(self.root, "pipe"))
        receipt = self.authorise("probe_path_alias", ("exists", "type", "size"), target="pipe")
        started = time.monotonic()
        result = self.executor.acquire(
            receipt, fields=("exists", "type", "size"), now=time.time())
        self.assertLess(time.monotonic() - started, 5.0, "the worker must not block")
        self.assertEqual({"exists": True, "type": "other", "size": None},
                         result.to_dict()["fields"])
        # reading it is refused: a FIFO is not a regular file
        receipt = self.authorise("read_file_alias", ("exists",),
                                 nonce="n2", task="t2", grant="g2", target="pipe")
        with self.assertRaises(PolicyViolation):
            self.executor.acquire(receipt, fields=("exists",), now=time.time())

    def test_field_maps_are_bounded_and_explicit(self):
        for operation in ("probe_path_alias", "read_file_alias", "list_dir_alias", "run_synthetic_command"):
            self.assertTrue(self.executor.fields_for(operation), operation)
        self.assertEqual((), self.executor.fields_for("host_shell"))


if __name__ == "__main__":
    unittest.main()
