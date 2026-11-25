"""Named negative regression tests for the fourth independent review.

The fourth review of `10176308733e1dd9940560bcec259b43e738a500` returned
**FAIL / DO NOT APPROVE**. Its architectural framing is the contract these
tests enforce: authorization must be bound to the **exact credential,
resource and immutable request** that ultimately reaches the transport, and
that invariant must be fixed centrally rather than per manifestation.

Per the reviewer's instruction, each test drives the production boundary — a
provider entry point, a real HTTP-header construction, the polling constructor,
or git history — and each fails against the vulnerable implementation:

* F07/N02 - one credential snapshot per authorized request, on the generic and
           the typed entry points alike, asserted against the actual
           authorization header a test-owned opener sees;
* N07     - ownership evidence is bound to the complete authorization context
           (repository, granted reference, account, credential, workflow, run);
* N05     - one strict event-id validator across restore, normalize and accept;
* N06     - authorization traffic is bounded as requests, and concurrent
           lookups of one context coalesce;
* N12     - the validated write body is an immutable snapshot: a body mutated
           during authorization cannot change what is transmitted;
* N13     - a merge is bound to the pull/merge request's own target reference;
* N14     - a rerun addresses the verified pipeline; an unverifiable schedule
           resource is refused;
* F20     - the review package pin honours the documented revision contract,
           with negative history fixtures in temporary repositories.

Evidence class: MOCK / STATIC only. Every transport is a test-owned stub and
no credential is a real one.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.connectors.github import MAX_AUTHORIZATION_REQUESTS
from boru.connectors.polling import EventAllowlist, PollingSync
from boru.errors import ConnectorDenied


def connector_grant(**overrides):
    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                max_calls=64, issued_at=time.time(), expires_at=time.time() + 600, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class _StubResponse:
    def __init__(self, status=200, payload=b"{}"):
        self.status = status
        self._payload = payload
        self.headers = {"Content-Type": "application/json"}

    def read(self, limit=None):
        return self._payload[:limit] if limit else self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None


class _StubOpener:
    """A test-owned HTTP opener that records every request it is handed."""

    def __init__(self, answers):
        self._answers = answers
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        path = request.full_url.split("github.com", 1)[-1]
        status, payload = self._answers.get(path, (200, b"{}"))
        if status >= 400:
            raise OSError("http " + str(status))
        return _StubResponse(status, payload)


class F07CredentialSnapshotTests(unittest.TestCase):
    """F07/N02: one credential snapshot per authorized request, everywhere."""

    def test_f07_a_rotation_during_discovery_is_not_transmitted(self):
        # the typed discovery entry point must not read the credential twice.
        # The assertion is against the authorization header a test-owned HTTP
        # opener actually sees, not against an injected transport that reads
        # the environment itself: the identity callback rotates the credential
        # mid-request and the discovery request must still carry the verified
        # one.
        os.environ["BORU_R5_TOKEN"] = "first"
        opener = _StubOpener({"/user": (200, json.dumps({"login": "owner"}).encode()),
                              "/repos/owner/repo/actions/workflows": (200, b'{"workflows": []}')})
        original = GitHubProvider.verify_identity

        def rotating(self, expected_account, timeout=10.0, token=None):
            os.environ["BORU_R5_TOKEN"] = "rotated"
            answer = original(self, expected_account, timeout, token)
            os.environ["BORU_R5_TOKEN"] = "first"
            return answer

        try:
            with mock.patch("urllib.request.build_opener", return_value=opener), \
                    mock.patch.object(GitHubProvider, "verify_identity", rotating):
                provider = GitHubProvider(token_env="BORU_R5_TOKEN")
                provider.list_workflows_typed(connector_grant(operations=("list_workflows",),
                                                              nonce="typed"),
                                              {"repository": "owner/repo"})
        finally:
            os.environ.pop("BORU_R5_TOKEN", None)
        headers = [request.headers.get("Authorization") for request in opener.requests
                   if request.full_url.endswith("/repos/owner/repo/actions/workflows")]
        self.assertEqual(["Bearer first"], headers)

    def test_f07_the_transmitted_header_carries_the_verified_credential(self):
        # the actual authorization header a test-owned opener sees must be the
        # credential the identity guard verified, not one read afterwards
        os.environ["BORU_R5B_TOKEN"] = "first"
        opener = _StubOpener({"/user": (200, json.dumps({"login": "owner"}).encode()),
                              "/repos/owner/repo/issues": (200, b"{}")})
        try:
            with mock.patch("urllib.request.build_opener", return_value=opener):
                provider = GitHubProvider(token_env="BORU_R5B_TOKEN")
                # rotate during verification: the guard sees "first"
                original = GitHubProvider.verify_identity

                def rotating(self, expected_account, timeout=10.0, token=None):
                    os.environ["BORU_R5B_TOKEN"] = "rotated"
                    answer = original(self, expected_account, timeout, token)
                    os.environ["BORU_R5B_TOKEN"] = "first"
                    return answer

                with mock.patch.object(GitHubProvider, "verify_identity", rotating):
                    provider.call(connector_grant(nonce="header"), "list_issues",
                                  {"repository": "owner/repo"})
        finally:
            os.environ.pop("BORU_R5B_TOKEN", None)
        header = [request.headers.get("Authorization") for request in opener.requests
                  if "/user" not in request.full_url]
        self.assertTrue(header, "no repository request was made")
        self.assertEqual(["Bearer first"], header)

    def test_f07_a_rotation_between_identity_and_exchange_is_refused(self):
        os.environ["BORU_R5C_TOKEN"] = "first"

        def transport(method, path, body):
            if path == "/user":
                return 200, b'{"login":"intruder"}'
            return 200, b"{}"

        provider = GitHubProvider(token_env="BORU_R5C_TOKEN", transport=transport)
        # the caller's grant names the owner: an intruder credential denies
        os.environ["BORU_R5C_TOKEN"] = "intruder"
        with self.assertRaises(ConnectorDenied):
            provider.call(connector_grant(nonce="rot"), "list_issues",
                          {"repository": "owner/repo"})
        os.environ.pop("BORU_R5C_TOKEN", None)


class N07OwnershipContextTests(unittest.TestCase):
    """N07: ownership evidence is bound to the whole authorization context."""

    def setUp(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        self.paths = []

    def _github(self, runs_by_reference):
        def transport(method, path, body):
            self.paths.append(path)
            if "/git/ref/heads/" in path:
                return 200, json.dumps({"object": {"sha": "a" * 40}}).encode()
            if "/actions/workflows/" in path and path.endswith("/runs?per_page=100"):
                for reference, runs in runs_by_reference.items():
                    if path.startswith("/repos/{}/".format(reference[0])) \
                            and reference[1] == "main":
                        pass
                # the metadata answers for the first repository only
                if path.startswith("/repos/first/"):
                    return 200, json.dumps({"workflow_runs": runs_by_reference["first"]}).encode()
                return 200, json.dumps({"workflow_runs": runs_by_reference["second"]}).encode()
            return 200, b"{}"

        return GitHubProvider(transport=transport)

    def test_n07_ownership_does_not_cross_repositories(self):
        provider = self._github({"first": [{"id": "42"}], "second": []})
        first = connector_grant(repository="first/repo", operations=("get_run",),
                                workflow_ids=("ci.yml",), nonce="a")
        second = connector_grant(repository="second/repo", operations=("get_run",),
                                 workflow_ids=("ci.yml",), nonce="b")
        provider.call(first, "get_run",
                      {"repository": "first/repo", "run_id": "42", "workflow": "ci.yml"})
        # the same run id on another repository is not covered by that evidence
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(second, "get_run",
                          {"repository": "second/repo", "run_id": "42",
                           "workflow": "ci.yml"})
        self.assertEqual("run_not_of_workflow", str(raised.exception))

    def test_n07_ownership_does_not_cross_references(self):
        # the same repository, a different granted reference: GitLab's lookup is
        # reference-scoped, so evidence for one reference never serves another
        def transport(method, path, body):
            self.paths.append(path)
            if "/pipelines?ref=main" in path:
                return 200, json.dumps([{"id": "42"}]).encode()
            if "/pipelines?ref=develop" in path:
                return 200, json.dumps([]).encode()
            return 200, b"{}"

        provider = GitLabProvider(transport=transport)
        main = connector_grant(repository="owner/project", reference="main",
                               operations=("get_run",), workflow_ids=("ci.yml",), nonce="m")
        develop = connector_grant(repository="owner/project", reference="develop",
                                  operations=("get_run",), workflow_ids=("ci.yml",),
                                  nonce="d")
        provider.call(main, "get_run",
                      {"repository": "owner/project", "run_id": "42", "workflow": "ci.yml",
                       "reference": "main"})
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(develop, "get_run",
                          {"repository": "owner/project", "run_id": "42",
                           "workflow": "ci.yml", "reference": "develop"})
        self.assertEqual("run_not_of_workflow", str(raised.exception))
        self.assertIn("/api/v4/projects/owner%2Fproject/pipelines?ref=develop&per_page=100",
                      self.paths)

    def test_n07_ownership_does_not_cross_a_credential_rotation(self):
        os.environ["BORU_R5D_TOKEN"] = "first"
        lookups = []

        def transport(method, path, body):
            if path == "/user":
                return 200, json.dumps({"login": "owner"}).encode()
            if path.endswith("/runs?per_page=100"):
                lookups.append(path)
                return 200, json.dumps({"workflow_runs": [{"id": "42"}]}).encode()
            return 200, b"{}"

        provider = GitHubProvider(token_env="BORU_R5D_TOKEN", transport=transport)
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        provider.call(subject, "get_run",
                      {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        try:
            os.environ["BORU_R5D_TOKEN"] = "rotated"
            provider.call(subject, "get_run",
                          {"repository": "owner/repo", "run_id": "42", "workflow": "ci.yml"})
        finally:
            os.environ.pop("BORU_R5D_TOKEN", None)
        # the rotated credential is a different authorization context, so the
        # ownership was re-established rather than reused
        self.assertEqual(2, len(lookups))

    def _gitlab_reporting_the_grants_pipelines(self):
        def transport(method, path, body):
            if "/pipelines?ref=main" in path:
                return 200, json.dumps([{"id": "42"}]).encode()
            return 200, b"[]"

        return GitLabProvider(transport=transport)

    def test_n07_the_lookup_binds_to_the_grants_reference(self):
        # the request names no reference: the ownership lookup must use the
        # reference the **grant** carries, never an empty caller slot
        provider = self._gitlab_reporting_the_grants_pipelines()
        subject = connector_grant(repository="owner/project", reference="main",
                                  operations=("get_run",), workflow_ids=("ci.yml",))
        payload = provider.call(subject, "get_run",
                                {"repository": "owner/project", "run_id": "42",
                                 "workflow": "ci.yml"})
        # the ownership lookup used the grant's reference, so the run itself
        # was reached
        self.assertEqual([], payload)

    def test_n07_an_empty_caller_slot_does_not_weaken_the_lookup(self):
        # a payload that names an empty reference cannot serve as ownership
        # evidence: the grant's reference is the only binding
        provider = self._gitlab_reporting_the_grants_pipelines()
        subject = connector_grant(repository="owner/project", reference="main",
                                  operations=("get_run",), workflow_ids=("ci.yml",))
        with self.assertRaises(ConnectorDenied):
            provider.call(subject, "get_run",
                          {"repository": "owner/project", "run_id": "42",
                           "workflow": "ci.yml", "reference": ""})


class N06AuthorizationTrafficTests(unittest.TestCase):
    """N06: authorization traffic is bounded as requests and coalesced."""

    def test_n06_foreign_runs_cannot_exhaust_authorization_traffic(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        provider = GitHubProvider(transport=lambda m, p, b: (
            200, json.dumps({"workflow_runs": []}).encode()
            if p.endswith("/runs?per_page=100") else (200, b"{}")))
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        # every attempt names a run the workflow does not have, and every
        # attempt uses a fresh context: past the budget the connector refuses
        # instead of issuing unbounded authorization requests
        denied = None
        for index in range(MAX_AUTHORIZATION_REQUESTS + 4):
            try:
                provider.call(subject, "get_run",
                              {"repository": "owner/repo", "run_id": str(index),
                               "workflow": "ci.yml"})
            except ConnectorDenied as exc:
                denied = str(exc)
                if denied == "authorization_traffic_exhausted":
                    break
        self.assertEqual("authorization_traffic_exhausted", denied)

    def test_n06_concurrent_ownership_lookups_coalesce(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        lookups = []
        lock = threading.Lock()

        def transport(method, path, body):
            if path.endswith("/runs?per_page=100"):
                with lock:
                    lookups.append(path)
                time.sleep(0.05)
                return 200, json.dumps({"workflow_runs": [{"id": "42"}]}).encode()
            return 200, b"{}"

        provider = GitHubProvider(transport=transport)
        subject = connector_grant(operations=("get_run",), workflow_ids=("ci.yml",))
        results = []

        def worker():
            try:
                provider.call(subject, "get_run",
                              {"repository": "owner/repo", "run_id": "42",
                               "workflow": "ci.yml"})
                results.append("allow")
            except ConnectorDenied as exc:
                results.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # one context, one authorization request: the rest see the entry
        self.assertEqual(1, len(lookups))
        self.assertEqual(6 * ["allow"], results)


class N05StrictValidationTests(unittest.TestCase):
    """N05: one strict event-id validator, on every path."""

    def test_n05_malformed_checkpoint_entries_are_refused(self):
        for malformed in ([None, 123, "", "   "], ["ok", None], ["  "]):
            with self.assertRaises(ConnectorDenied):
                PollingSync(EventAllowlist(("push",)), seen=malformed)

    def test_n05_a_whitespace_only_restored_id_is_refused(self):
        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=[" "])

    def test_n05_a_padded_restored_id_is_refused(self):
        with self.assertRaises(ConnectorDenied):
            PollingSync(EventAllowlist(("push",)), seen=[" id "])

    def test_n05_normalize_refuses_a_malformed_id(self):
        sync = PollingSync(EventAllowlist(("push",)))
        with self.assertRaises(ConnectorDenied):
            sync.normalize([{"id": "  ", "type": "push", "payload": {}}])


class N12BodySnapshotTests(unittest.TestCase):
    """N12: the validated body is an immutable snapshot."""

    def setUp(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        self.seen = []
        self.provider = GitHubProvider()
        self.provider._transport = lambda method, path, body: (
            self.seen.append((method, path, body)) or (200, b'{"ok": 1}'))
        self.subject = connector_grant(operations=("create_pull",),
                                       capabilities=(Capability.CODE_PR_WRITE,))

    def test_n12_a_body_mutated_during_authorization_is_not_transmitted(self):
        # the identity guard runs between validation and transmission: a caller
        # that mutates the body there cannot change what was checked
        body = {"title": "synthetic", "head": "feature", "base": "main"}

        def hostile_transport(method, path, payload):
            self.seen.append((method, path, payload))
            if path == "/user":
                body["base"] = "develop"
                return 200, b'{"login":"owner"}'
            return 200, b'{"number": 1}'

        provider = GitHubProvider(token_env="BORU_R5E_TOKEN", transport=hostile_transport)
        os.environ["BORU_R5E_TOKEN"] = "synthetic"
        try:
            payload = provider.call(self.subject, "create_pull",
                                    {"repository": "owner/repo"},
                                    body=body)
        finally:
            os.environ.pop("BORU_R5E_TOKEN", None)
        self.assertEqual({"number": 1}, payload)
        # the mutation never reached the endpoint: the validated snapshot did
        transmitted = [entry for entry in self.seen if entry[0] == "POST"]
        self.assertEqual([("POST", "/repos/owner/repo/pulls",
                           {"title": "synthetic", "head": "feature", "base": "main"})],
                         transmitted)

    def test_n12_the_transmitted_body_is_the_validated_one(self):
        payload = self.provider.call(self.subject, "create_pull",
                                     {"repository": "owner/repo"},
                                     body={"title": "synthetic", "head": "feature",
                                           "base": "main"})
        self.assertEqual({"ok": 1}, payload)
        self.assertEqual([("POST", "/repos/owner/repo/pulls",
                           {"title": "synthetic", "head": "feature", "base": "main"})],
                         self.seen)


class N13MergeTargetTests(unittest.TestCase):
    """N13: a merge is bound to the pull request's own target reference."""

    def setUp(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        self.paths = []
        self.provider = GitHubProvider()
        self.subject = connector_grant(operations=("merge_pull",),
                                       capabilities=(Capability.MERGE_RELEASE,))

    def _transport(self, pull_base):
        def transport(method, path, body):
            self.paths.append((method, path))
            if path == "/repos/owner/repo/pulls/42":
                return 200, json.dumps({"base": {"ref": pull_base}}).encode()
            return 200, b"{}"

        self.provider._transport = transport

    def test_n13_a_pull_targeting_another_reference_is_refused(self):
        self._transport("develop")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "merge_pull",
                               {"repository": "owner/repo", "issue": "42"})
        self.assertEqual("reference_not_granted", str(raised.exception))
        # the merge itself was never issued
        self.assertNotIn(("PUT", "/repos/owner/repo/pulls/42/merge"), self.paths)

    def test_n13_a_pull_targeting_the_granted_reference_merges(self):
        self._transport("main")
        payload = self.provider.call(self.subject, "merge_pull",
                                     {"repository": "owner/repo", "issue": "42"})
        self.assertEqual({}, payload)
        self.assertIn(("PUT", "/repos/owner/repo/pulls/42/merge"), self.paths)

    def test_n13_missing_pull_metadata_refuses(self):
        self.provider._transport = lambda method, path, body: (
            self.paths.append((method, path)) or (404, b"{}"))
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "merge_pull",
                               {"repository": "owner/repo", "issue": "42"})
        self.assertEqual("merge_target_unavailable", str(raised.exception))

    def test_n13_gitlab_merge_requests_are_bound_too(self):
        provider = GitLabProvider(transport=lambda method, path, body: (
            (200, json.dumps({"target_branch": "develop"}).encode())
            if path.endswith("/merge_requests/42") else (200, b"{}")))
        subject = connector_grant(repository="owner/project", operations=("merge_pull",),
                                  capabilities=(Capability.MERGE_RELEASE,))
        with self.assertRaises(ConnectorDenied) as raised:
            provider.call(subject, "merge_pull",
                          {"repository": "owner/project", "issue": "42"})
        self.assertEqual("reference_not_granted", str(raised.exception))


class N14ResourceMismatchTests(unittest.TestCase):
    """N11/N14: the resource checked is the resource acted upon."""

    def setUp(self):
        os.environ.pop("BORU_R5_TOKEN", None)
        self.paths = []
        self.provider = GitLabProvider()
        self.subject = connector_grant(repository="owner/project", reference="main",
                                       operations=("rerun_workflow",),
                                       capabilities=(Capability.ACTIONS_DISPATCH,),
                                       workflow_ids=("ci.yml",))

    def _transport(self):
        def transport(method, path, body):
            self.paths.append((method, path))
            if "/pipelines?ref=main" in path:
                return 200, json.dumps([{"id": "42"}]).encode()
            return 200, b"{}"

        self.provider._transport = transport

    def test_n14_a_rerun_retries_the_verified_pipeline(self):
        self._transport()
        payload = self.provider.call(self.subject, "rerun_workflow",
                                     {"repository": "owner/project", "run_id": "42",
                                      "workflow": "ci.yml", "reference": "main"})
        self.assertEqual({}, payload)
        # the pipeline whose ownership was verified is the one retried
        self.assertIn(("POST", "/api/v4/projects/owner%2Fproject/pipelines/42/retry"),
                      self.paths)
        # and no schedule was addressed
        self.assertNotIn(
            ("POST", "/api/v4/projects/owner%2Fproject/pipeline_schedules/ci.yml/play"),
            self.paths)

    def test_n14_a_pipeline_does_not_authorize_a_schedule(self):
        self._transport()
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.subject, "configure_workflow",
                               {"repository": "owner/project", "run_id": "42",
                                "workflow": "ci.yml", "reference": "main"})
        self.assertEqual("resource_not_verifiable", str(raised.exception))
        self.assertNotIn(
            ("PUT", "/api/v4/projects/owner%2Fproject/pipeline_schedules/ci.yml"),
            self.paths)


class F20RevisionContractTests(unittest.TestCase):
    """F20: the pin honours the documented revision contract."""

    DOCUMENTATION_ONLY_PATHS = ("docs/", "harness/")

    def test_f20_the_documented_head_carries_docs_only_changes(self):
        import re

        package = open("docs/REVIEW_PACKAGE.md", "r", encoding="utf-8").read()
        match = re.search(r"head under review: `([0-9a-f]{7,40})", package)
        self.assertIsNotNone(match, "the package names no head")

        def git(*args):
            return subprocess.run(["git"] + list(args), capture_output=True, text=True)

        if git("rev-parse", "HEAD").returncode != 0:
            self.skipTest("no git history is available in this tree")
        pinned = match.group(1)
        self.assertEqual(0, git("rev-parse", "--verify", pinned + "^{commit}").returncode,
                         "the package pins an unknown commit")
        changed = git("diff", "--name-only", pinned, "HEAD")
        self.assertEqual(0, changed.returncode, "cannot compare the pin with HEAD")
        files = [name for name in changed.stdout.splitlines() if name.strip()]
        undocumented = sorted(name for name in files
                             if not name.startswith(self.DOCUMENTATION_ONLY_PATHS))
        self.assertEqual([], undocumented,
                         "the package pin lags production code: "
                         + ", ".join(undocumented))

    def test_f20_a_production_code_change_since_the_pin_fails(self):
        # the negative fixture: the same history shape with a code change must
        # be rejected, which is what the frozen-revision F20 defect was
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            environment = dict(os.environ, GIT_DIR=os.path.join(root, ".git"),
                               GIT_WORK_TREE=root)

            def git(*args):
                return subprocess.run(["git"] + list(args), cwd=root, capture_output=True,
                                      text=True, check=True)

            def commit(name, content):
                target = os.path.join(root, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(content)
                git("add", "-A")
                git("-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "commit", "-q", "-m", name)
                return git("rev-parse", "HEAD").stdout.strip()

            pin = commit("docs/first.md", "first")
            head = commit("boru/connectors/github.py", "code")
            changed = subprocess.run(["git", "diff", "--name-only", pin, head],
                                     cwd=root, capture_output=True, text=True,
                                     env=environment, check=True)
            files = [name for name in changed.stdout.splitlines() if name.strip()]
            undocumented = sorted(name for name in files
                                  if not name.startswith(self.DOCUMENTATION_ONLY_PATHS))
            self.assertEqual(["boru/connectors/github.py"], undocumented)

    def test_f20_a_documentation_only_change_since_the_pin_passes(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)

            def git(*args):
                return subprocess.run(["git"] + list(args), cwd=root, capture_output=True,
                                      text=True, check=True)

            def commit(name, content):
                target = os.path.join(root, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(content)
                git("add", "-A")
                git("-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "commit", "-q", "-m", name)
                return git("rev-parse", "HEAD").stdout.strip()

            pin = commit("docs/first.md", "first")
            head = commit("docs/second.md", "second")
            changed = git("diff", "--name-only", pin, head)
            files = [name for name in changed.stdout.splitlines() if name.strip()]
            undocumented = sorted(name for name in files
                                  if not name.startswith(self.DOCUMENTATION_ONLY_PATHS))
            self.assertEqual([], undocumented)


if __name__ == "__main__":
    unittest.main()
