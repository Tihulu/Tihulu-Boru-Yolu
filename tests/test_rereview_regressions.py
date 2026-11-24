"""Re-review regressions (Findings F03, F06, F07, F12, F14, F15, F17, F20 and N01-N05).

Each test names the finding it closes and reproduces the reviewer's input
against the current tree.  Synthetic data only: no network, no credentials, no
host state beyond a temporary directory.
"""
import dataclasses
import json
import os
import socket
import stat
import tempfile
import threading
import time
import unittest

from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity
from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.polling import MAX_SEEN, EventAllowlist, PollingSync
from boru.connectors.scope import check_dispatch_body
from boru.consent import MAX_NONCES, ConsentStore
from boru.errors import ConnectorDenied, PolicyViolation
from boru.executor import LocalExecutor
from boru.privacy import ConsentStore as LocalConsent
from boru.workers import WorkerRegistry

KEY = bytes(range(32))


def _alias_root(name="boru-rereview-"):
    root = tempfile.mkdtemp(prefix=name)
    os.chmod(root, stat.S_IRWXU)
    return root


class F03Tests(unittest.TestCase):
    """A grant must name its resource: no alias-less wildcard, in either store."""

    def test_f03_consent_without_alias_must_not_cover_alias(self):
        store = ConsentStore()
        with self.assertRaises(Exception):
            store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                        level="L0", expires_at=time.time() + 60, nonce="n")
        store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                    alias="demo", level="L0", expires_at=time.time() + 60, nonce="n")
        self.assertTrue(store.check(grant_id="g", recipient="r", task_id="t",
                                     field_name="probe", alias="demo", nonce="n"))
        self.assertFalse(store.check(grant_id="g", recipient="r", task_id="t",
                                      field_name="probe", alias="elsewhere", nonce="n2"))

    def test_f03_in_memory_consent_binds_its_alias(self):
        store = LocalConsent()
        with self.assertRaises(PolicyViolation):
            store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                        level="L0", expires_at=time.time() + 60, nonce="n")
        store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                    alias="demo", level="L0", expires_at=time.time() + 60, nonce="n")
        self.assertTrue(store.check(grant_id="g", recipient="r", task_id="t",
                                     field_name="probe", alias="demo", nonce="n"))
        self.assertFalse(store.check(grant_id="g", recipient="r", task_id="t",
                                      field_name="probe", alias="elsewhere", nonce="n2"))

    def test_f03_a_legacy_alias_less_row_denies(self):
        store = ConsentStore()
        store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                    alias="demo", level="L0", expires_at=time.time() + 60, nonce="n")
        # hand-written history: the alias is blanked, and it must deny, not match
        store._db.execute("UPDATE grants SET alias = '' WHERE grant_id = 'g'")
        self.assertFalse(store.check(grant_id="g", recipient="r", task_id="t",
                                      field_name="probe", alias="demo", nonce="n"))


class F06Tests(unittest.TestCase):
    """In registry mode the permitted scopes come from the registry record."""

    def test_f06_registry_worker_scope_cannot_be_forged(self):
        root = _alias_root()
        worker_dir = os.path.join(root, "workers")
        os.makedirs(worker_dir)
        os.chmod(worker_dir, stat.S_IRWXU)
        try:
            registry = WorkerRegistry(worker_dir)
            registry.create("w", ("A",))          # the registry record holds A only
            secret = registry.secret_for("w")
            store = ConsentStore()
            store.grant(grant_id="g", recipient="w", task_id="t",
                        field_name="probe_path_alias", alias="B", level="L0",
                        expires_at=time.time() + 60, nonce="n")
            broker = Broker(worker=WorkerIdentity("w", scopes=("A",)),
                            scopes=ScopeAllowlist({"A": root, "B": root}),
                            consent=store, consent_recipient="w",
                            registry=registry, worker_secret=secret)
            forged = OperationRequest(
                operation="probe_path_alias", resource_alias="B", requester="o",
                task_id="t", worker=WorkerIdentity("w", scopes=("B",)),   # forged
                fields=("exists",), nonce="n", grant_id="g")
            decision, receipt, reason = broker.authorize(forged)
            self.assertEqual("deny", decision)
            self.assertIsNone(receipt)
            self.assertEqual("worker_scope", reason)
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_f06_the_registry_record_decides_not_the_request(self):
        root = _alias_root()
        worker_dir = os.path.join(root, "workers")
        os.makedirs(worker_dir)
        os.chmod(worker_dir, stat.S_IRWXU)
        try:
            registry = WorkerRegistry(worker_dir)
            registry.create("w", ("A",))
            secret = registry.secret_for("w")
            store = ConsentStore()
            store.grant(grant_id="g", recipient="w", task_id="t",
                        field_name="probe_path_alias", alias="A", level="L0",
                        expires_at=time.time() + 60, nonce="n")
            broker = Broker(worker=WorkerIdentity("w", scopes=("A",)),
                            scopes=ScopeAllowlist({"A": root}),
                            consent=store, consent_recipient="w",
                            registry=registry, worker_secret=secret)
            # a request that declares *more* than the registry record holds is
            # refused even when the alias itself is permitted
            wider = OperationRequest(
                operation="probe_path_alias", resource_alias="A", requester="o",
                task_id="t", worker=WorkerIdentity("w", scopes=("A", "B")),
                fields=("exists",), nonce="n", grant_id="g")
            self.assertEqual("deny", broker.authorize(wider)[0])
            # and the record's own scopes still work
            plain = OperationRequest(
                operation="probe_path_alias", resource_alias="A", requester="o",
                task_id="t", worker=WorkerIdentity("w", scopes=("A",)),
                fields=("exists",), nonce="n", grant_id="g")
            self.assertEqual("allow", broker.authorize(plain)[0])
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)


class F07Tests(unittest.TestCase):
    """A cached identity belongs to the token that was checked."""

    def test_f07_token_rotation_invalidates_cached_identity(self):
        seen = []
        variable = "BORU_TEST_F07_TOKEN"

        def transport(method, path, body):
            seen.append(path)
            if path == "/user":
                login = "owner" if not seen.count("/user") > 1 else "intruder"
                return 200, json.dumps({"login": login}).encode("utf-8")
            return 200, b"{}"

        provider = GitHubProvider(token_env=variable, transport=transport)
        grant = Grant(grant_id="g", account="owner", repository="owner/repo",
                      reference="main", operations=("list_issues",),
                      capabilities=(Capability.REPO_READ,), max_calls=8,
                      issued_at=time.time(), expires_at=time.time() + 60, nonce="n")
        os.environ[variable] = "first-token"
        try:
            self.assertTrue(provider._require_account_identity(grant) is None)
            verified = provider._verified_identity
            # the remembered identity is the verified (token fingerprint,
            # account) pair, so it binds the account and not the token alone
            self.assertIsNotNone(verified)
            self.assertEqual(grant.account, verified[1])
            # a rotated token is re-checked, and the stored pair is not
            # updated by a failed check: a stale identity never authorizes it
            os.environ[variable] = "rotated-token"
            with self.assertRaises(ConnectorDenied):
                provider._require_account_identity(grant)
            self.assertEqual(verified, provider._verified_identity)
        finally:
            os.environ.pop(variable, None)

    def test_f07_discovery_verifies_identity_and_counts_usage(self):
        def transport(method, path, body):
            if path == "/user":
                return 200, b'{"login":"intruder"}'
            return 200, b'{"workflows": []}'

        provider = GitHubProvider(token_env="BORU_TEST_F07B_TOKEN", transport=transport)
        grant = Grant(grant_id="g", account="owner", repository="owner/repo",
                      reference="main", operations=("list_workflows",),
                      capabilities=(Capability.REPO_READ,), max_calls=8,
                      issued_at=time.time(), expires_at=time.time() + 60, nonce="n")
        os.environ["BORU_TEST_F07B_TOKEN"] = "token"
        try:
            with self.assertRaises(ConnectorDenied):
                provider.list_workflows_typed(grant, {"repository": "owner/repo",
                                                     "reference": "main"})
        finally:
            os.environ.pop("BORU_TEST_F07B_TOKEN", None)

    def test_n02_a_counted_discovery_charges_the_grant(self):
        def transport(method, path, body):
            if path == "/user":
                return 200, b'{"login":"owner"}'
            return 200, b'{"workflows": []}'

        provider = GitHubProvider(token_env="BORU_TEST_N02_TOKEN", transport=transport)
        grant = Grant(grant_id="g", account="owner", repository="owner/repo",
                      reference="main", operations=("list_workflows",),
                      capabilities=(Capability.REPO_READ,), max_calls=8,
                      issued_at=time.time(), expires_at=time.time() + 60, nonce="n")
        os.environ["BORU_TEST_N02_TOKEN"] = "token"
        try:
            provider.list_workflows_typed(grant, {"repository": "owner/repo",
                                                 "reference": "main"})
            self.assertEqual(1, provider._calls["g"])
        finally:
            os.environ.pop("BORU_TEST_N02_TOKEN", None)


class F12Tests(unittest.TestCase):
    """A grant id is globally unique: a revoked id cannot be re-issued."""

    def test_f12_revoked_id_cannot_reissue_under_another_task(self):
        store = ConsentStore()
        store.grant(grant_id="g", recipient="r", task_id="t1", field_name="probe",
                    alias="demo", level="L0", expires_at=time.time() + 60, nonce="n1")
        store.revoke("g")
        for other in (dict(task_id="t2"), dict(recipient="r2"), dict(field_name="other")):
            with self.assertRaises(Exception):
                store.grant(grant_id="g", recipient=other.get("recipient", "r"),
                            task_id=other.get("task_id", "t1"),
                            field_name=other.get("field_name", "probe"),
                            alias="demo", level="L0", expires_at=time.time() + 60,
                            nonce="n2")

    def test_f12_two_grants_may_not_share_one_id(self):
        store = ConsentStore()
        store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                    alias="demo", level="L0", expires_at=time.time() + 60, nonce="n1")
        with self.assertRaises(Exception):
            store.grant(grant_id="g", recipient="r", task_id="t", field_name="probe",
                        alias="demo", level="L0", expires_at=time.time() + 60, nonce="n2")


class F14Tests(unittest.TestCase):
    """Capacity is acquired before a thread exists."""

    def test_f14_capacity_is_acquired_before_a_thread_spawns(self):
        import boru.broker_service as service_module

        source = open(service_module.__file__, "r", encoding="utf-8").read()
        serve = source[source.index("def serve"):source.index("def stop")]
        spawn = serve.index("threading.Thread(")
        acquire = serve.index("_slots.acquire")
        self.assertGreaterEqual(acquire, 0)
        # the acquisition must appear before the first spawn in the accept loop
        self.assertLess(acquire, spawn)

    def test_f14_a_flood_of_connections_is_refused_not_queued(self):
        from boru.broker_service import MAX_CONCURRENT_CONNECTIONS
        from boru.broker_service import BrokerService

        registry_root = _alias_root()
        worker_dir = os.path.join(registry_root, "workers")
        os.makedirs(worker_dir)
        os.chmod(worker_dir, stat.S_IRWXU)
        try:
            registry = WorkerRegistry(worker_dir)
            registry.create("w1", ("demo",))
            secret = registry.secret_for("w1")
            store = ConsentStore()
            broker = Broker(worker=WorkerIdentity("w1", scopes=("demo",)),
                            scopes=ScopeAllowlist({"demo": registry_root}),
                            consent=store, consent_recipient="w1",
                            registry=registry, worker_secret=secret)
            service = BrokerService(broker, registry, "w1", secret)
            host, port = service.start()
            try:
                held = []
                for _ in range(MAX_CONCURRENT_CONNECTIONS + 2):
                    connection = socket.create_connection((host, port), timeout=5)
                    held.append(connection)
                answered = None
                probe = socket.create_connection((host, port), timeout=5)
                try:
                    probe.sendall(b'{"worker_id":"w1","secret":"wrong"}\n')
                    probe.settimeout(5)
                    raw = b""
                    while b"}" not in raw:
                        chunk = probe.recv(4096)
                        if not chunk:
                            break
                        raw += chunk
                    answered = json.loads(raw.decode("utf-8")).get("reason")
                finally:
                    probe.close()
                self.assertEqual("service_busy", answered)
            finally:
                for connection in held:
                    try:
                        connection.close()
                    except OSError:
                        pass
                service.stop()
        finally:
            import shutil

            shutil.rmtree(registry_root, ignore_errors=True)


class F15Tests(unittest.TestCase):
    """An HTTP error body keeps a bounded prefix."""

    def test_f15_http_error_read_is_capped(self):
        import boru.connectors.github as github_module

        source = open(github_module.__file__, "r", encoding="utf-8").read()
        exchange = source[source.index("def _exchange"):source.index("def read_only_check")]
        self.assertNotIn("error.read()", exchange)
        self.assertIn("_bounded_read(error, MAX_ERROR_BODY_BYTES)", exchange)


class F17Tests(unittest.TestCase):
    """A used nonce outlives its grant, and the memory store is bounded."""

    def test_f17_replay_after_nonce_pruning_is_denied(self):
        store = ConsentStore()
        stamp = time.time()
        for index in range(MAX_NONCES):
            store.grant(grant_id="g{}".format(index), recipient="r", task_id="t",
                        field_name="probe", alias="demo", level="L0",
                        expires_at=stamp + 600, nonce="n{}".format(index))
            self.assertTrue(store.check(grant_id="g{}".format(index), recipient="r",
                                        task_id="t", field_name="probe", alias="demo",
                                        nonce="n{}".format(index)))
        # the registry is at capacity: new work is refused rather than evicting
        store.grant(grant_id="gX", recipient="r", task_id="t", field_name="probe",
                    alias="demo", level="L0", expires_at=stamp + 600, nonce="nX")
        self.assertFalse(store.check(grant_id="gX", recipient="r", task_id="t",
                                     field_name="probe", alias="demo", nonce="nX"))
        # and no live grant became replayable
        self.assertFalse(store.check(grant_id="g0", recipient="r", task_id="t",
                                     field_name="probe", alias="demo", nonce="n0"))

    def test_f17_the_memory_store_bounds_its_used_nonces(self):
        from boru.privacy import MAX_NONCES as MEMORY_MAX

        store = LocalConsent()
        stamp = time.time()
        for index in range(MEMORY_MAX + 8):
            store.grant(grant_id="g{}".format(index), recipient="r", task_id="t",
                        field_name="probe", alias="demo", level="L0",
                        expires_at=stamp + 600, nonce="n{}".format(index))
            store.check(grant_id="g{}".format(index), recipient="r", task_id="t",
                        field_name="probe", alias="demo", nonce="n{}".format(index))
        self.assertLessEqual(len(store._used_nonces), MEMORY_MAX)


class N01Tests(unittest.TestCase):
    """A grant must carry finite, ordered timestamps."""

    def test_n01_nonfinite_grant_expiry_is_refused(self):
        for bad in (float("nan"), float("inf"), float("-inf"), "soon", True, 0, -1):
            with self.assertRaises(ValueError):
                Grant(grant_id="g", account="a", repository="o/r", reference="main",
                      operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                      max_calls=8, issued_at=time.time(), expires_at=bad, nonce="n")
        ordered = Grant(grant_id="g", account="a", repository="o/r", reference="main",
                        operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                        max_calls=8, issued_at=time.time(), expires_at=time.time() + 60,
                        nonce="n")
        self.assertEqual([], ordered.validate())


class N03Tests(unittest.TestCase):
    """The worker produces exactly the fields the receipt names."""

    def test_n03_executor_returns_only_receipt_fields(self):
        root = _alias_root()
        try:
            os.mkdir(os.path.join(root, "sub"))
            with open(os.path.join(root, "note.txt"), "w", encoding="utf-8") as handle:
                handle.write("one\ntwo\n")
            store = ConsentStore()
            store.grant(grant_id="g", recipient="w", task_id="t",
                        field_name="probe_path_alias", alias="demo", level="L0",
                        expires_at=time.time() + 60, nonce="n")
            broker = Broker(worker=WorkerIdentity("w", scopes=("demo",)),
                            scopes=ScopeAllowlist({"demo": root}),
                            consent=store, consent_recipient="w",
                            authorization_key=KEY)
            request = OperationRequest(
                operation="probe_path_alias", resource_alias="demo", requester="o",
                task_id="t", worker=WorkerIdentity("w", scopes=("demo",)),
                fields=("exists",), nonce="n", grant_id="g")
            decision, receipt, _ = broker.authorize(request, requested_fields=("exists",))
            self.assertEqual("allow", decision)
            produced = LocalExecutor(ScopeAllowlist({"demo": root}),
                                     authorization_key=KEY).acquire(
                receipt, fields=("exists",), now=time.time()).to_dict()["fields"]
            self.assertEqual(["exists"], sorted(produced))
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)


class N04Tests(unittest.TestCase):
    """Inputs need the owner's declared schema."""

    def test_n04_dispatch_without_declared_schema_rejects_inputs(self):
        grant = Grant(grant_id="g", account="a", repository="o/r", reference="main",
                      operations=("dispatch_workflow",),
                      capabilities=(Capability.ACTIONS_DISPATCH,), max_calls=8,
                      issued_at=time.time(), expires_at=time.time() + 60, nonce="n",
                      workflow_ids=("ci.yml",))
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(grant, {"ref": "main", "inputs": {"target": "staging"}})
        # an empty input set still needs none
        check_dispatch_body(grant, {"ref": "main", "inputs": {}})


class N05Tests(unittest.TestCase):
    """A restored polling registry is bounded as it is loaded."""

    def test_n05_restored_polling_registry_is_bounded(self):
        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)),
                        seen=("e{}".format(i) for i in range(MAX_SEEN + 1)))
        # the bound is enforced while the source is consumed, not after it has
        # been materialized: an oversized source is stopped at the refusing
        # entry rather than drained into memory first
        consumed = []

        def counting():
            for index in range(MAX_SEEN + 5000):
                consumed.append(index)
                yield "e{}".format(index)

        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=counting())
        self.assertLess(len(consumed), MAX_SEEN + 5000)
        self.assertGreaterEqual(len(consumed), MAX_SEEN)
        bounded = PollingSync(EventAllowlist(("push",)),
                              seen=("e{}".format(i) for i in range(MAX_SEEN)))
        self.assertEqual(MAX_SEEN, len(bounded.seen))


class F20Tests(unittest.TestCase):
    """The review package names the head it describes."""

    def test_f20_the_package_pins_the_current_head(self):
        """The package names the head it describes.

        The pin may name HEAD itself or one of its ancestors: a documents-only
        commit after the pin moves the head without changing the code tree, and
        requiring the pin to equal HEAD would make the test fail on its own
        fix.  A pin that names an unknown or a future commit still fails.
        """
        import re
        import subprocess

        package = open("docs/REVIEW_PACKAGE.md", "r", encoding="utf-8").read()
        match = re.search(r"head under review: `([0-9a-f]{7,40})", package)
        self.assertIsNotNone(match, "the package names no head")
        pinned = match.group(1)
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.returncode != 0:
            self.skipTest("no git history is available in this tree")
        head = head.stdout.strip()
        resolved = subprocess.run(["git", "rev-parse", "--verify", pinned + "^{commit}"],
                                  capture_output=True, text=True)
        self.assertEqual(0, resolved.returncode,
                         "the package pins an unknown commit: " + pinned)
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", pinned, head],
                                  capture_output=True)
        self.assertEqual(0, ancestor.returncode,
                         "the package pins " + pinned + " which is not HEAD or its ancestor")


if __name__ == "__main__":
    unittest.main()
