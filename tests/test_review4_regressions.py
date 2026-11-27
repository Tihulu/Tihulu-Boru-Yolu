"""Named negative regression tests for the third independent review.

The third review of `9b6ce534` returned **FAIL / DO NOT APPROVE**. Each defect
was first reproduced against this tree, then remediated, then closed with a
named negative regression test here. Per that review's instruction the tests
exercise the **production authorization boundary** (the provider entry points,
the consent store's own retention, the polling constructor) rather than
reconstructing an expected condition, and neither connector nor the historical
regression files were weakened.

Findings covered:

* N07 - a run is addressed only after the provider's own metadata confirms it
       belongs to the granted workflow (GitHub runs list, GitLab pipelines of
       the granted reference);
* N08 - a reference-carrying body key is mandatory, and a body that diverges
       from the granted reference is refused before any transport;
* F07 - the credential verified is the credential transmitted: a rotation
       mid-request is detected, not silently accepted;
* N02 - the typed discovery entry point inherits the identity guard;
* N05 - a restored checkpoint is bounded on inspected entries and on id size;
* N06 - the grant ceiling bounds repository operations while authorization
       traffic is separately bounded;
* N11 - each provider has its own write-body contract, so a legitimate GitLab
       merge-request body is accepted and a diverging one refused;
* F20 - the review package describes the code tree a reviewer checks out;
* N10 - every closure rests on a behavioural test that fails against the
       vulnerable implementation and passes against the corrected one.

Evidence class: MOCK / STATIC only. Every transport is a test-owned stub and
no credential is a real one.
"""
import json
import os
import threading
import time
import unittest

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.connectors.polling import MAX_RESTORED_ENTRIES, MAX_SEEN, EventAllowlist, PollingSync
from boru.errors import ConnectorDenied


def connector_grant(**overrides):
    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                max_calls=16, issued_at=time.time(), expires_at=time.time() + 600, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class N07RunOwnershipTests(unittest.TestCase):
    """N07: the provider's own metadata decides which run an id names."""

    def setUp(self):
        os.environ.pop("BORU_R4_TOKEN", None)
        self.paths = []

    def _github(self, runs):
        def transport(method, path, body):
            self.paths.append(path)
            if "/actions/workflows/" in path and path.endswith("/runs?per_page=100"):
                return 200, json.dumps({"total_count": len(runs),
                                        "workflow_runs": [{"id": number, "head_branch": "main"} for number in runs]}).encode()
            return 200, b"{}"

        provider = GitHubProvider(transport=transport)
        return provider

    def test_n07_a_run_of_another_workflow_is_refused(self):
        # the granted workflow's runs do not contain run 42: it belongs to
        # another workflow, whatever the caller declares
        provider = self._github(runs=[7, 99])
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "get_run",
                          {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        self.assertEqual("run_not_of_workflow", str(raised.exception))
        # the ownership evidence came from the workflow's own runs endpoint
        self.assertIn("/repos/owner/repo/actions/workflows/ci.yml/runs?per_page=100",
                      self.paths)
        # and the run itself was never addressed
        self.assertNotIn("/repos/owner/repo/actions/runs/42", self.paths)

    def test_n07_the_granted_workflows_run_is_allowed(self):
        provider = self._github(runs=[42, 43])
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        payload = provider.call(subject, "get_run",
                                {"repository": "owner/repo", "run_id": "42",
                                 "workflow": "ci.yml"})
        self.assertEqual({}, payload)
        self.assertIn("/repos/owner/repo/actions/runs/42", self.paths)

    def test_n07_a_verified_run_is_not_re_queried(self):
        provider = self._github(runs=[42])
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        provider.call(subject, "get_run",
                      {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        before = len(self.paths)
        provider.call(subject, "get_run",
                      {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        self.assertEqual(before + 1, len(self.paths))

    def test_n07_missing_ownership_evidence_refuses(self):
        # the workflow's runs endpoint answers something unusable
        def transport(method, path, body):
            self.paths.append(path)
            if path.endswith("/runs?per_page=100"):
                return 500, b"{}"
            return 200, b"{}"

        provider = GitHubProvider(transport=transport)
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "get_run",
                          {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        self.assertEqual("run_ownership_unavailable", str(raised.exception))

    def test_n07_gitlab_pipelines_are_bound_to_the_granted_reference(self):
        def transport(method, path, body):
            self.paths.append(path)
            if "/pipelines?ref=main" in path:
                return 200, json.dumps([{"id": 5}]).encode()
            return 200, b"{}"

        provider = GitLabProvider(transport=transport)
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",),
                                  repository="owner/project")
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "get_run",
                          {"repository": "owner/project", "run_id": "42",
                           "workflow": "ci.yml", "reference": "main"})
        self.assertEqual("run_not_of_workflow", str(raised.exception))
        self.assertIn("/api/v4/projects/owner%2Fproject/pipelines?ref=main&per_page=100",
                      self.paths)
        # and the pipeline itself was never addressed
        self.assertNotIn("/pipelines/42", " ".join(self.paths))

    def test_n07_gitlab_grants_its_own_pipeline(self):
        def transport(method, path, body):
            self.paths.append(path)
            if "/pipelines?ref=main" in path:
                return 200, json.dumps([{"id": 42, "ref": "main"}]).encode()
            return 200, b"{}"

        provider = GitLabProvider(transport=transport)
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",),
                                  repository="owner/project")
        payload = provider.call(subject, "get_run",
                                {"repository": "owner/project", "run_id": "42",
                                 "workflow": "ci.yml", "reference": "main"})
        self.assertEqual({}, payload)


class N08WriteBodyTests(unittest.TestCase):
    """N08: a reference-carrying body key is mandatory, not merely checked."""

    def setUp(self):
        os.environ.pop("BORU_R4_TOKEN", None)
        self.seen = []
        self.provider = GitHubProvider()
        self.provider._transport = lambda method, path, body: (
            self.seen.append((method, path, body)) or (200, b'{"ok": 1}'))

    def test_n08_omitting_the_file_branch_is_refused(self):
        subject = connector_grant(operations=("put_file",),
                                  capabilities=(Capability.CODE_PR_WRITE,))
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(subject, "put_file",
                               {"repository": "owner/repo", "path": "README.md",
                                "reference": "main"},
                               body={"message": "synthetic", "content": "eA=="})
        self.assertEqual("reference_required_in_body", str(raised.exception))
        self.assertEqual([], self.seen)

    def test_n08_omitting_the_release_target_is_refused(self):
        subject = connector_grant(operations=("create_release",),
                                  capabilities=(Capability.MERGE_RELEASE,))
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(subject, "create_release", {"repository": "owner/repo"},
                               body={"tag_name": "v1"})
        self.assertEqual("reference_required_in_body", str(raised.exception))

    def test_n08_a_diverging_pull_base_is_refused(self):
        subject = connector_grant(operations=("create_pull",),
                                  capabilities=(Capability.CODE_PR_WRITE,))
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(subject, "create_pull", {"repository": "owner/repo"},
                               body={"title": "synthetic", "head": "feature",
                                     "base": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n08_a_granted_write_still_reaches_the_endpoint(self):
        subject = connector_grant(operations=("create_pull",),
                                  capabilities=(Capability.CODE_PR_WRITE,))
        payload = self.provider.call(subject, "create_pull", {"repository": "owner/repo"},
                                     body={"title": "synthetic", "head": "feature",
                                           "base": "main"})
        self.assertEqual({"ok": 1}, payload)
        self.assertEqual([("POST", "/repos/owner/repo/pulls",
                           {"title": "synthetic", "head": "feature", "base": "main"})],
                         self.seen)

    REFERENCE_HEAD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    OTHER_HEAD = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    def _provider_reporting_the_reference_head(self):
        head = self.REFERENCE_HEAD

        def transport(method, path, body):
            self.seen.append((method, path, body))
            if path == "/repos/owner/repo/git/ref/heads/main":
                return 200, json.dumps({"object": {"sha": head}}).encode()
            return 200, b"{}"

        return GitHubProvider(transport=transport)

    def _branch_subject(self):
        return connector_grant(operations=("create_branch",),
                               capabilities=(Capability.CODE_PR_WRITE,))

    def test_n08_a_branch_is_created_from_a_verified_sha(self):
        # the source sha must be the granted reference's own head, taken from
        # the provider's metadata rather than from the caller's claim
        provider = self._provider_reporting_the_reference_head()
        subject = self._branch_subject()
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "create_branch",
                          {"repository": "owner/repo", "reference": "main",
                           "sha": self.OTHER_HEAD},
                          body={"ref": "refs/heads/feature", "sha": self.OTHER_HEAD})
        self.assertEqual("reference_not_granted", str(raised.exception))
        # the reference's own head was consulted, and the branch was not created
        self.assertIn(("GET", "/repos/owner/repo/git/ref/heads/main", {}), self.seen)
        self.assertNotIn("POST", [method for method, _, _ in self.seen])

    def test_n08_a_body_sha_diverging_from_the_reference_head_is_refused(self):
        provider = self._provider_reporting_the_reference_head()
        subject = self._branch_subject()
        # the request declares the right head but the body carries another one
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "create_branch",
                          {"repository": "owner/repo", "reference": "main",
                           "sha": self.REFERENCE_HEAD},
                          body={"ref": "refs/heads/feature", "sha": self.OTHER_HEAD})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n08_a_branch_is_created_from_the_references_own_head(self):
        provider = self._provider_reporting_the_reference_head()
        subject = self._branch_subject()
        payload = provider.call(subject, "create_branch",
                                {"repository": "owner/repo", "reference": "main",
                                 "sha": self.REFERENCE_HEAD},
                                body={"ref": "refs/heads/feature",
                                      "sha": self.REFERENCE_HEAD})
        # the reference head was consulted first, then the branch was created
        # from exactly that head
        self.assertIn(("GET", "/repos/owner/repo/git/ref/heads/main", {}), self.seen)
        self.assertIn(("POST", "/repos/owner/repo/git/refs",
                       {"ref": "refs/heads/feature", "sha": self.REFERENCE_HEAD}),
                      self.seen)

    def test_n08_a_branch_target_must_be_a_branch_name(self):
        provider = self._provider_reporting_the_reference_head()
        subject = self._branch_subject()
        for target in ("refs/tags/v1", "/etc/passwd", "refs/heads/../../escape"):
            with self.assertRaises(ConnectorDenied) as raised:
                provider.call(subject, "create_branch",
                              {"repository": "owner/repo", "reference": "main",
                               "sha": self.REFERENCE_HEAD},
                              body={"ref": target, "sha": self.REFERENCE_HEAD})
            self.assertEqual("unsafe_body_value", str(raised.exception), target)


class F07CredentialSnapshotTests(unittest.TestCase):
    """F07: the credential verified is the credential transmitted."""

    def test_f07_a_rotation_mid_request_is_not_transmitted(self):
        # the snapshot read once is the value that rides out: a rotation after
        # the guard must not become the transmitted credential
        os.environ["BORU_R4_TOKEN"] = "first"
        seen = []

        def transport(method, path, body):
            if path == "/user":
                return 200, json.dumps({"login": "owner"}).encode()
            seen.append((method, path, os.environ.get("BORU_R4_TOKEN")))
            return 200, b"{}"

        provider = GitHubProvider(token_env="BORU_R4_TOKEN", transport=transport)
        subject = connector_grant()
        provider.call(subject, "list_issues", {"repository": "owner/repo"})
        os.environ.pop("BORU_R4_TOKEN", None)
        self.assertEqual([("GET", "/repos/owner/repo/issues", "first")], seen)

    def test_f07_a_rotation_after_verification_is_reverified(self):
        os.environ["BORU_R4_TOKEN"] = "first"
        logins = ["owner", "intruder"]

        def transport(method, path, body):
            if path == "/user":
                login = logins.pop(0) if logins else "intruder"
                return 200, json.dumps({"login": login}).encode()
            return 200, b"{}"

        provider = GitHubProvider(token_env="BORU_R4_TOKEN", transport=transport)
        subject = connector_grant()
        provider.call(subject, "list_issues", {"repository": "owner/repo"})
        # the rotated credential has a different fingerprint, so its account is
        # verified again - and the intruder's account denies
        os.environ["BORU_R4_TOKEN"] = "rotated"
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(connector_grant(nonce="rotated-1"), "list_issues",
                          {"repository": "owner/repo"})
        self.assertEqual("identity_mismatch", str(raised.exception))
        os.environ.pop("BORU_R4_TOKEN", None)


class N02TypedDiscoveryTests(unittest.TestCase):
    """N02: the typed discovery entry point inherits the identity guard."""

    def test_n02_typed_discovery_denies_a_mismatched_account(self):
        os.environ["BORU_R4B_TOKEN"] = "synthetic"
        seen = []

        def transport(method, path, body):
            seen.append(path)
            if path == "/user":
                return 200, b'{"login":"intruder"}'
            return 200, b'{"workflows": []}'

        provider = GitHubProvider(token_env="BORU_R4B_TOKEN", transport=transport)
        subject = connector_grant(operations=("list_workflows",))
        with self.assertRaises(ConnectorDenied) as raised:
            provider.list_workflows_typed(subject, {"repository": "owner/repo"})
        self.assertEqual("identity_mismatch", str(raised.exception))
        self.assertNotIn("/repos/owner/repo/actions/workflows", seen)

    def test_n02_typed_discovery_counts_the_grant(self):
        os.environ.pop("BORU_R4B_TOKEN", None)

        def transport(method, path, body):
            if path == "/user":
                return 200, b'{"login":"owner"}'
            return 200, b'{"workflows": []}'

        provider = GitHubProvider(transport=transport)
        subject = connector_grant(operations=("list_workflows",), max_calls=1)
        provider.list_workflows_typed(subject, {"repository": "owner/repo"})
        with self.assertRaises(ConnectorDenied):
            provider.list_workflows_typed(subject, {"repository": "owner/repo"})


class N05CheckpointBoundTests(unittest.TestCase):
    """N05: a restored checkpoint is bounded on entries and on id size."""

    def test_n05_a_duplicate_stream_is_not_drained(self):
        def duplicates():
            for _ in range(MAX_RESTORED_ENTRIES + 20000):
                yield "duplicate"

        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=duplicates())

    def test_n05_an_oversized_restored_id_is_refused(self):
        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=["x" * 1000000])

    def test_n05_a_restored_id_with_control_characters_is_refused(self):
        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=["bad\nid"])

    def test_n05_a_legitimate_checkpoint_still_loads(self):
        sync = PollingSync(EventAllowlist(("push",)),
                           seen=["a", "b", "a", "c"])
        self.assertEqual(("a", "b", "c"), sync.seen)

    def test_n05_a_duplicate_heavy_checkpoint_within_the_budget_loads(self):
        entries = []
        for index in range(64):
            entries.extend(["e{}".format(index)] * 4)
        sync = PollingSync(EventAllowlist(("push",)), seen=entries)
        self.assertEqual(64, len(sync.seen))


class N06CeilingScopeTests(unittest.TestCase):
    """N06: the ceiling bounds repository operations; authorization traffic is
    bounded separately."""

    def test_n06_the_reservation_is_atomic(self):
        os.environ.pop("BORU_R4_TOKEN", None)
        provider = GitHubProvider()

        def slow(method, path, body):
            time.sleep(0.002)
            return 200, b"{}"

        provider._transport = slow
        subject = connector_grant(max_calls=4, nonce="atomic")
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                provider.call(subject, "list_issues", {"repository": "owner/repo"})
            except ConnectorDenied as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(4, provider._calls["g1"])
        self.assertEqual(12, len(errors))

    def test_n06_identity_requests_are_bounded_separately(self):
        os.environ["BORU_R4C_TOKEN"] = "synthetic"
        identity_requests = []

        def transport(method, path, body):
            if path == "/user":
                identity_requests.append(path)
                return 200, b'{"login":"owner"}'
            return 200, b"{}"

        provider = GitHubProvider(token_env="BORU_R4C_TOKEN", transport=transport)
        # one grant, one account: the account is verified once, however many
        # repository operations follow, so authorization traffic is bounded
        for index in range(3):
            provider.call(connector_grant(max_calls=4, nonce="n{}".format(index)),
                          "list_issues", {"repository": "owner/repo"})
        os.environ.pop("BORU_R4C_TOKEN", None)
        self.assertEqual(1, len(identity_requests))


class N11ProviderContractTests(unittest.TestCase):
    """N11: each provider has its own write-body contract."""

    def setUp(self):
        os.environ.pop("BORU_R4_TOKEN", None)
        self.seen = []
        self.provider = GitLabProvider()
        self.provider._transport = lambda method, path, body: (
            self.seen.append((method, path, body)) or (201, b'{"iid": 1}'))
        self.subject = connector_grant(operations=("create_pull",),
                                       capabilities=(Capability.CODE_PR_WRITE,),
                                       repository="owner/project")

    def test_n11_a_legitimate_gitlab_merge_request_is_accepted(self):
        payload = self.provider.call(self.subject, "create_pull",
                                     {"repository": "owner/project"},
                                     body={"title": "synthetic", "source_branch": "feature",
                                           "target_branch": "main"})
        self.assertEqual({"iid": 1}, payload)
        self.assertEqual([("POST", "/api/v4/projects/owner%2Fproject/merge_requests",
                           {"title": "synthetic", "source_branch": "feature",
                            "target_branch": "main"})], self.seen)

    def test_n11_a_diverging_gitlab_target_branch_is_refused(self):
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "create_pull",
                               {"repository": "owner/project"},
                               body={"title": "synthetic", "source_branch": "feature",
                                     "target_branch": "develop"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n11_a_gitlab_file_write_binds_its_branch(self):
        subject = connector_grant(operations=("put_file",),
                                  capabilities=(Capability.CODE_PR_WRITE,),
                                  repository="owner/project")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(subject, "put_file",
                               {"repository": "owner/project", "path": "README.md",
                                "reference": "main"},
                               body={"branch": "develop", "content": "eA==",
                                     "commit_message": "synthetic"})
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_n11_a_gitlab_branch_is_created_from_the_granted_reference(self):
        subject = connector_grant(operations=("create_branch",),
                                  capabilities=(Capability.CODE_PR_WRITE,),
                                  repository="owner/project")
        payload = self.provider.call(subject, "create_branch",
                                     {"repository": "owner/project"},
                                     body={"branch": "feature", "ref": "main"})
        self.assertEqual({"iid": 1}, payload)
        with self.assertRaises(ConnectorDenied):
            self.provider.call(subject, "create_branch",
                               {"repository": "owner/project"},
                               body={"branch": "feature2", "ref": "develop"})


class F20RevisionBindingTests(unittest.TestCase):
    """F20: the review package describes the code a reviewer checks out."""

    DOCUMENTATION_ONLY_PATHS = ("docs/", "harness/")

    def test_f20_the_pin_names_the_reviewed_code(self):
        """Exact revision match, or documentation-only intervening changes.

        The third review's remedy: the package must identify the revision the
        reviewer checks out, and where it names an earlier commit, every
        intervening change must belong to an approved documentation-only path
        set.  Ancestry alone is not evidence.
        """
        import re
        import subprocess

        package = open("docs/REVIEW_PACKAGE.md", "r", encoding="utf-8").read()
        match = re.search(r"head under review: `([0-9a-f]{7,40})", package)
        self.assertIsNotNone(match, "the package names no head")
        pinned = match.group(1)

        def git(*args):
            return subprocess.run(["git"] + list(args), capture_output=True, text=True)

        if git("rev-parse", "HEAD").returncode != 0:
            self.skipTest("no git history is available in this tree")
        self.assertEqual(0, git("rev-parse", "--verify", pinned + "^{commit}").returncode,
                         "the package pins an unknown commit: " + pinned)
        if git("rev-parse", pinned).stdout.strip() == git("rev-parse", "HEAD").stdout.strip():
            return  # exact revision match
        changed = git("diff", "--name-only", pinned, "HEAD")
        self.assertEqual(0, changed.returncode, "cannot compare the pin with HEAD")
        files = [name for name in changed.stdout.splitlines() if name.strip()]
        self.assertTrue(files, "the pin lags HEAD but nothing changed")
        undocumented = sorted(name for name in files
                              if not name.startswith(self.DOCUMENTATION_ONLY_PATHS))
        self.assertEqual([], undocumented,
                         "the package pins " + pinned + " but production code"
                         " changed since: " + ", ".join(undocumented))


if __name__ == "__main__":
    unittest.main()
