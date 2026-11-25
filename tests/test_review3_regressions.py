"""Named negative regression tests for the second re-review findings.

Each test reproduces one defect the independent reviewer demonstrated against
head ``cedb56fb`` and asserts the remediated behaviour. The reviewer's
requirement was explicit: named negative behavioural tests for every finding,
exercised against **both** repository connectors and **both** consent stores.

Findings covered here:

* F03  - a check that omits its recipient can never match a grant (persistent
         and in-memory stores);
* F07  - the connector identity guard binds the verified account and never
         passes a configured-but-absent credential (GitHub **and** GitLab);
* F12  - a revoked grant id cannot be reissued under another task or recipient
         in the in-memory store, as in the persistent one;
* F17  - a nonce migrated with no expiry can expire through normal retention;
* N02  - workflow discovery inherits the same identity guard as any other
         externally connected path;
* N05  - a restored polling registry is bounded while it is consumed;
* N06  - a grant's call ceiling is reserved atomically before any transport,
         so concurrent calls cannot exceed it (GitHub **and** GitLab);
* N07  - a run id alone is never sufficient: the granted workflow scopes it;
* N08  - a write body cannot carry a reference the grant did not authorize;
* N09  - a future-issued grant is not usable.

Evidence class: MOCK / STATIC only. No provider is contacted; every transport
is a test-owned stub and no credential is a real one.
"""
import os
import sqlite3
import stat
import tempfile
import threading
import time
import unittest

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.connectors.polling import MAX_SEEN, EventAllowlist, PollingSync
from boru.connectors.scope import check_write_body
from boru.consent import ConsentStore as PersistentConsent
from boru.errors import ConnectorDenied, PolicyViolation
from boru.privacy import ConsentStore as LocalConsent

USER_PATHS = {"github": "/user", "gitlab": "/api/v4/user"}


def connector_grant(**overrides):
    """A synthetic grant; every value is test-owned, never a real account."""
    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                max_calls=8, issued_at=time.time(), expires_at=time.time() + 600, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class F03RecipientBindingTests(unittest.TestCase):
    """F03: a check must name its recipient; an omitted one never matches."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-f03-")
        os.chmod(self.root, stat.S_IRWXU)
        self.path = os.path.join(self.root, "consents.sqlite")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_f03_persistent_check_without_recipient_matches_no_grant(self):
        with PersistentConsent(self.path) as store:
            store.grant(grant_id="g", recipient="alice", task_id="t", field_name="excerpt",
                        alias="demo", level="L2", expires_at=time.time() + 600, nonce="n")
            # the omission that used to match any recipient's grant
            self.assertFalse(store.check(grant_id="g", recipient="", task_id="t",
                                         field_name="excerpt", alias="demo", nonce="fresh"))
            # and the recipient is now a required argument: there is no query
            # in this store that cannot name one
            with self.assertRaises(TypeError):
                store.check(grant_id="g", task_id="t", field_name="excerpt",
                            alias="demo", nonce="fresh")
            # the correctly named recipient still works
            self.assertTrue(store.check(grant_id="g", recipient="alice", task_id="t",
                                        field_name="excerpt", alias="demo", nonce="n"))

    def test_f03_local_check_binds_its_recipient(self):
        store = LocalConsent()
        store.grant(grant_id="g", recipient="alice", task_id="t", field_name="excerpt",
                    alias="demo", level="L2", expires_at=time.time() + 600, nonce="n")
        self.assertFalse(store.check(grant_id="g", recipient="bob", task_id="t",
                                     field_name="excerpt", alias="demo", nonce="n2"))
        self.assertTrue(store.check(grant_id="g", recipient="alice", task_id="t",
                                    field_name="excerpt", alias="demo", nonce="n"))

    def test_f03_broker_requires_its_consent_recipient(self):
        from boru.broker import Broker, ScopeAllowlist, WorkerIdentity

        with PersistentConsent(self.path) as consent:
            consent.grant(grant_id="g", recipient="w1", task_id="t", field_name="probe_path_alias",
                          alias="demo", level="L0", expires_at=time.time() + 600, nonce="n")
            with self.assertRaises(PolicyViolation):
                Broker(worker=WorkerIdentity("w1", scopes=("demo",)),
                       scopes=ScopeAllowlist({"demo": self.root}),
                       consent=consent, consent_recipient="")


class F07IdentityGuardTests(unittest.TestCase):
    """F07/N02: the identity guard binds the account and the credential."""

    def _provider(self, name, token, transport):
        if name == "github":
            return GitHubProvider(token_env="BORU_R3_TOKEN", transport=transport)
        return GitLabProvider(token_env="BORU_R3_TOKEN", transport=transport)

    def test_f07_second_account_behind_one_token_is_reverified(self):
        for name in ("github", "gitlab"):
            with self.subTest(provider=name):
                os.environ["BORU_R3_TOKEN"] = "synthetic-token"
                calls = []

                def transport(method, path, body):
                    calls.append(path)
                    if path == USER_PATHS[name]:
                        return 200, b'{"login":"owner","username":"owner"}'
                    return 200, b"{}"

                provider = self._provider(name, "synthetic-token", transport)
                provider.call(connector_grant(nonce="a"), "list_issues",
                              {"repository": "owner/repo"})
                self.assertTrue(provider.audit())
                # a second grant naming another account behind the same token is
                # re-verified, never waved through on the first verification
                with self.assertRaises(ConnectorDenied):
                    provider.call(connector_grant(account="intruder", nonce="b"), "list_issues",
                                  {"repository": "owner/repo"})

    def test_f07_a_configured_but_absent_credential_never_passes(self):
        for name in ("github", "gitlab"):
            with self.subTest(provider=name):
                provider = self._provider(name, None, lambda m, p, b: (200, b"{}"))
                os.environ.pop("BORU_R3_TOKEN", None)
                with self.assertRaises(ConnectorDenied) as raised:
                    provider.call(connector_grant(nonce="c"), "list_issues",
                                  {"repository": "owner/repo"})
                self.assertEqual("credential_missing", str(raised.exception))

    def test_n02_discovery_inherits_the_identity_guard(self):
        # discovery is an externally connected path like any other (N02): it
        # verifies the account behind the token before the request
        for name in ("github", "gitlab"):
            with self.subTest(provider=name):
                os.environ["BORU_R3_TOKEN"] = "synthetic-token"
                def transport(method, route, body):
                    if route == USER_PATHS[name]:
                        return 200, b'{"login":"intruder","username":"intruder"}'
                    return 200, b'{"workflows": []}'

                provider = self._provider(name, None, transport)
                subject = connector_grant(operations=("list_workflows",), nonce="d")
                with self.assertRaises(ConnectorDenied) as raised:
                    provider.call(subject, "list_workflows", {"repository": "owner/repo"})
                self.assertEqual("identity_mismatch", str(raised.exception))


class F12ConsentIdentityTests(unittest.TestCase):
    """F12: a grant id is globally unique in the in-memory store as well."""

    def test_f12_revoked_id_cannot_be_reissued_under_another_task(self):
        store = LocalConsent()
        store.grant(grant_id="g", recipient="cloud", task_id="t1", field_name="excerpt",
                    alias="demo", level="L2", expires_at=time.time() + 600, nonce="n1")
        store.revoke("g")
        self.assertFalse(store.check(grant_id="g", recipient="cloud", task_id="t1",
                                     field_name="excerpt", alias="demo", nonce="n1"))
        with self.assertRaises(PolicyViolation):
            store.grant(grant_id="g", recipient="cloud", task_id="t2", field_name="excerpt",
                        alias="demo", level="L2", expires_at=time.time() + 600, nonce="n2")
        with self.assertRaises(PolicyViolation):
            store.grant(grant_id="g", recipient="other", task_id="t1", field_name="excerpt",
                        alias="demo", level="L2", expires_at=time.time() + 600, nonce="n3")

    def test_f12_revoked_id_cannot_be_reissued_under_another_field(self):
        store = LocalConsent()
        store.grant(grant_id="g", recipient="cloud", task_id="t1", field_name="excerpt",
                    alias="demo", level="L2", expires_at=time.time() + 600, nonce="n1")
        store.revoke("g")
        with self.assertRaises(PolicyViolation):
            store.grant(grant_id="g", recipient="cloud", task_id="t1", field_name="status",
                        alias="demo", level="L2", expires_at=time.time() + 600, nonce="n4")

    def test_f12_a_live_grant_still_binds_every_field(self):
        store = LocalConsent()
        store.grant(grant_id="g", recipient="cloud", task_id="t1", field_name="excerpt",
                    alias="demo", level="L2", expires_at=time.time() + 600, nonce="n1")
        self.assertTrue(store.check(grant_id="g", recipient="cloud", task_id="t1",
                                    field_name="excerpt", alias="demo", nonce="n1"))
        self.assertFalse(store.check(grant_id="g", recipient="cloud", task_id="other",
                                     field_name="excerpt", alias="demo", nonce="n1"))
        self.assertFalse(store.check(grant_id="g", recipient="cloud", task_id="t1",
                                     field_name="status", alias="demo", nonce="n1"))


class F17MigratedNonceTests(unittest.TestCase):
    """F17: a nonce migrated with no expiry can expire through retention."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-f17-")
        os.chmod(self.root, stat.S_IRWXU)
        self.path = os.path.join(self.root, "consents.sqlite")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def _write_v2_store(self):
        connection = sqlite3.connect(self.path)
        connection.executescript("""
CREATE TABLE grants (
    grant_id TEXT NOT NULL PRIMARY KEY, recipient TEXT NOT NULL, task_id TEXT NOT NULL,
    field_name TEXT NOT NULL, alias TEXT, level TEXT NOT NULL, expires_at REAL NOT NULL,
    nonce TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, issued_at REAL NOT NULL
);
CREATE TABLE used_nonces (
    nonce TEXT PRIMARY KEY, used_at REAL NOT NULL, expires_at REAL NOT NULL DEFAULT 0
);
""")
        connection.execute(
            "INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("g-live", "cloud", "t", "excerpt", "demo", "L2",
             time.time() + 600, "live-nonce", 0, time.time()))
        connection.execute("INSERT INTO used_nonces VALUES(?,?,?)",
                           ("live-nonce", time.time(), 0))
        connection.execute("INSERT INTO used_nonces VALUES(?,?,?)",
                           ("orphan-nonce", time.time(), 0))
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
        connection.close()
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def test_f17_migration_binds_the_grant_expiry(self):
        self._write_v2_store()
        with PersistentConsent(self.path) as store:
            rows = dict(store._db.execute(
                "SELECT nonce, expires_at FROM used_nonces").fetchall())
            # the live nonce outlives the grant that carried it
            self.assertGreater(rows["live-nonce"], time.time())
            # an orphan carries no grant: it is prunable, not immortal
            self.assertLessEqual(rows["orphan-nonce"], time.time())

    def test_f17_an_expired_grant_nonce_can_be_pruned(self):
        self._write_v2_store()
        with PersistentConsent(self.path) as store:
            # retention runs at *now*: a live grant's nonce stays, an orphan's
            # row is prunable, and the bound cannot be filled by rows that no
            # grant can ever justify
            used = store._db.execute(
                "DELETE FROM used_nonces WHERE (expires_at > 0 AND expires_at < ?)"
                " OR (expires_at <= 0 AND used_at < ?)",
                (time.time(), time.time())).rowcount
            remaining = sorted(row[0] for row in store._db.execute(
                "SELECT nonce FROM used_nonces").fetchall())
            self.assertGreater(used, 0)
            # the live one stays, the orphan goes: the bound cannot be filled
            # forever by rows no grant can ever justify
            self.assertEqual(["live-nonce"], remaining)


class N05BoundedRestoreTests(unittest.TestCase):
    """N05: a restored registry is bounded while it is consumed."""

    def test_n05_an_oversized_source_is_not_materialized(self):
        consumed = []

        def counting():
            for index in range(MAX_SEEN + 5000):
                consumed.append(index)
                yield "e{}".format(index)

        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=counting())
        # the source is stopped at the refusing entry, not drained first
        self.assertLess(len(consumed), MAX_SEEN + 5000)
        self.assertGreaterEqual(len(consumed), MAX_SEEN)

    def test_n05_a_bounded_restore_still_loads(self):
        sync = PollingSync(EventAllowlist(("push",)),
                           seen=("e{}".format(i) for i in range(MAX_SEEN)))
        self.assertEqual(MAX_SEEN, len(sync.seen))


class N06CallCeilingTests(unittest.TestCase):
    """N06: a call ceiling is reserved atomically before any transport."""

    def _race(self, provider, grant):
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                provider.call(grant, "list_issues", {"repository": "owner/repo"})
            except ConnectorDenied as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return errors

    def test_n06_github_concurrent_calls_never_exceed_the_ceiling(self):
        os.environ.pop("BORU_R3_TOKEN", None)
        provider = GitHubProvider()

        def slow(method, path, body):
            time.sleep(0.002)
            return 200, b"{}"

        provider._transport = slow
        subject = connector_grant(max_calls=5, nonce="race")
        errors = self._race(provider, subject)
        self.assertEqual(5, provider._calls["g1"])
        self.assertEqual(19, len(errors))
        self.assertTrue(all("grant_exhausted" == reason for reason in errors))

    def test_n06_gitlab_concurrent_calls_never_exceed_the_ceiling(self):
        os.environ.pop("BORU_R3_TOKEN", None)
        provider = GitLabProvider()

        def slow(method, path, body):
            time.sleep(0.002)
            return 200, b"{}"

        provider._transport = slow
        subject = connector_grant(max_calls=4, nonce="race")
        errors = self._race(provider, subject)
        self.assertEqual(4, provider._calls["g1"])
        self.assertEqual(20, len(errors))


class N07RunScopeTests(unittest.TestCase):
    """N07: a run is addressed only through its granted workflow."""

    def setUp(self):
        os.environ.pop("BORU_R3_TOKEN", None)
        self.provider = GitHubProvider()
        self.provider._transport = lambda m, p, b: (200, b"{}")
        self.subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",),
                                       nonce="run")

    def test_n07_a_run_id_alone_is_refused(self):
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "get_run",
                               {"repository": "owner/repo", "run_id": "42"})
        self.assertEqual("workflow_required", str(raised.exception))

    def test_n07_a_run_of_another_workflow_is_refused(self):
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "get_run",
                               {"repository": "owner/repo", "run_id": "42",
                                "workflow": "other.yml"})
        self.assertEqual("workflow_not_granted", str(raised.exception))

    def test_n07_the_granted_workflow_scopes_the_run(self):
        # the workflow's own runs list confirms run 42 belongs to it, and only
        # then is the run addressed
        self.provider._transport = lambda method, path, body: (
            (200, b'{"workflow_runs": [{"id": "42"}]}')
            if path.endswith("/runs?per_page=100") else (200, b'{}'))
        payload = self.provider.call(self.subject, "get_run",
                                     {"repository": "owner/repo", "run_id": "42",
                                      "workflow": "ci.yml"})
        self.assertEqual({}, payload)


class N08WriteBodyTests(unittest.TestCase):
    """N08: a write body can never carry another reference than the granted one."""

    def setUp(self):
        os.environ.pop("BORU_R3_TOKEN", None)

    def test_n08_pull_base_must_be_the_granted_reference(self):
        subject = connector_grant(operations=("create_pull",),
                                  capabilities=(Capability.CODE_PR_WRITE,), nonce="pr")
        provider = GitHubProvider()
        provider._transport = lambda m, p, b: (201, b'{"number": 1}')
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "create_pull", {"repository": "owner/repo"},
                          body={"title": "synthetic", "head": "feature", "base": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n08_file_write_branch_must_be_the_granted_reference(self):
        subject = connector_grant(operations=("put_file",),
                                  capabilities=(Capability.CODE_PR_WRITE,), nonce="pf")
        provider = GitHubProvider()
        provider._transport = lambda m, p, b: (200, b'{"content": {}}')
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "put_file", {"repository": "owner/repo", "path": "README.md",
                                                "reference": "main", "branch": "main"},
                          body={"message": "synthetic", "content": "eA==", "branch": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n08_a_write_body_carries_only_documented_keys(self):
        subject = connector_grant(operations=("create_pull",),
                                  capabilities=(Capability.CODE_PR_WRITE,), nonce="pr2")
        with self.assertRaises(ConnectorDenied) as raised:
            check_write_body(subject, "create_pull",
                             {"title": "synthetic", "head": "feature", "base": "main",
                              "smuggled": "value"})
        self.assertEqual("body_unknown_key", str(raised.exception))

    def test_n08_a_release_target_must_be_the_granted_reference(self):
        subject = connector_grant(operations=("create_release",),
                                  capabilities=(Capability.MERGE_RELEASE,), nonce="rel")
        with self.assertRaises(ConnectorDenied) as raised:
            check_write_body(subject, "create_release",
                             {"tag_name": "v1", "target_commitish": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n08_gitlab_write_bodies_are_checked_too(self):
        subject = connector_grant(operations=("create_pull",),
                                  capabilities=(Capability.CODE_PR_WRITE,), nonce="gl-pr",
                                  repository="owner/project")
        provider = GitLabProvider()
        provider._transport = lambda m, p, b: (201, b'{"iid": 1}')
        # GitLab's own field names are the documented ones, and a target
        # branch the grant did not authorize is refused (N11)
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "create_pull", {"repository": "owner/project"},
                          body={"title": "synthetic", "source_branch": "feature",
                                "target_branch": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))


class N09GrantValidityTests(unittest.TestCase):
    """N09: a grant is usable only between its own bounds."""

    def test_n09_a_future_issued_grant_is_not_usable(self):
        now = time.time()
        subject = connector_grant(issued_at=now + 3600, expires_at=now + 7200, nonce="fut")
        self.assertEqual((False, "grant_not_yet_valid"), subject.permits("list_issues", now, 0))

    def test_n09_a_grant_becomes_usable_at_its_issued_at(self):
        now = time.time()
        subject = connector_grant(issued_at=now, expires_at=now + 3600, nonce="live")
        self.assertEqual((True, ""), subject.permits("list_issues", now, 0))

    def test_n09_the_expiry_still_follows_the_issue(self):
        now = time.time()
        with self.assertRaises(ValueError):
            connector_grant(issued_at=now + 3600, expires_at=now + 10, nonce="bad")


if __name__ == "__main__":
    unittest.main()
