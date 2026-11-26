"""Regression probes for the review-six request boundary."""
import unittest
from collections.abc import Mapping
from types import SimpleNamespace

from boru.connectors.request import freeze_mapping, wire_body
from boru.connectors.scope import check_call


class ChangingMapping(Mapping):
    def __init__(self):
        self.reads = 0

    def __iter__(self):
        return iter(("repository",))

    def __len__(self):
        return 1

    def __getitem__(self, key):
        self.reads += 1
        return "owner/repo" if self.reads == 1 else "owner/other"


class RequestBoundaryTests(unittest.TestCase):
    def test_scope_does_not_reread_caller_mapping(self):
        payload = ChangingMapping()
        grant = SimpleNamespace(repository="owner/repo", reference="main", grant_id="g")
        slots = check_call(grant, "list_issues", payload, method=None, path="",
                           default_method="GET")
        self.assertEqual("owner/repo", slots["repository"])
        self.assertEqual(1, payload.reads)

    def test_json_arrays_and_objects_remain_distinct(self):
        body = {"empty": [], "object": {}, "labels": ["bug", "ab"],
                "nested": [["x", "y"], {"x": []}]}
        snap = freeze_mapping(body)
        body["labels"].append("mutation")
        self.assertEqual({"empty": [], "object": {}, "labels": ["bug", "ab"],
                          "nested": [["x", "y"], {"x": []}]}, wire_body(snap))
        with self.assertRaises(TypeError):
            snap["labels"] = ()


class ProviderBoundaryTests(unittest.TestCase):
    def grant(self, **overrides):
        import time
        from boru.connectors.base import Capability, Grant
        values = dict(grant_id="r6", account="owner", repository="owner/repo",
                      reference="main", operations=("get_run",),
                      capabilities=(Capability.REPO_READ,), workflow_ids=("ci.yml",),
                      max_calls=32, issued_at=time.time(), expires_at=time.time()+600,
                      nonce="r6")
        values.update(overrides)
        return Grant(**values)

    def test_github_cross_branch_and_missing_branch_are_refused(self):
        import json
        from boru.connectors.github import GitHubProvider
        from boru.errors import ConnectorDenied
        for metadata, reason in [({"id": 42, "head_branch": "develop"}, "reference_not_granted"),
                                 ({"id": 42}, "run_ownership_unavailable")]:
            with self.subTest(metadata=metadata):
                paths = []
                def transport(method, path, body):
                    paths.append(path)
                    return 200, json.dumps({"workflow_runs": [metadata]}).encode()
                provider = GitHubProvider(transport=transport)
                with self.assertRaisesRegex(ConnectorDenied, reason):
                    provider.call(self.grant(), "get_run", {"repository": "owner/repo",
                                  "run_id": "42", "workflow": "ci.yml"})
                self.assertNotIn("/repos/owner/repo/actions/runs/42", paths)

    def test_merge_retargeting_is_not_cached(self):
        import json
        from boru.connectors.base import Capability
        from boru.connectors.github import GitHubProvider
        from boru.connectors.gitlab import GitLabProvider
        from boru.errors import ConnectorDenied
        for provider_type, repo in [(GitHubProvider, "owner/repo"),
                                    (GitLabProvider, "owner/project")]:
            with self.subTest(provider=provider_type.__name__):
                paths = []
                target = ["main"]
                def transport(method, path, body):
                    paths.append((method, path))
                    if method == "GET":
                        result = ({"base": {"ref": target[0]}} if provider_type is GitHubProvider
                                  else {"target_branch": target[0]})
                        return 200, json.dumps(result).encode()
                    return 200, b"{}"
                provider = provider_type(transport=transport)
                grant = self.grant(repository=repo, operations=("merge_pull",),
                                   capabilities=(Capability.MERGE_RELEASE,))
                payload = {"repository": repo, "issue": "42"}
                provider.call(grant, "merge_pull", payload)
                target[0] = "develop"
                with self.assertRaisesRegex(ConnectorDenied, "reference_not_granted"):
                    provider.call(grant, "merge_pull", payload)
                self.assertEqual(2, sum(method == "GET" for method, _ in paths))
                self.assertEqual(1, sum(method != "GET" for method, _ in paths))

    def test_failed_branch_source_requests_consume_budget(self):
        from unittest.mock import patch
        from boru.connectors.base import Capability
        from boru.connectors.github import GitHubProvider
        from boru.errors import ConnectorDenied
        calls = []
        def transport(method, path, body):
            calls.append(path)
            return 404, b"{}"
        provider = GitHubProvider(transport=transport)
        grant = self.grant(operations=("create_branch",),
                           capabilities=(Capability.CODE_PR_WRITE,))
        payload = {"repository": "owner/repo"}
        body = {"ref": "refs/heads/feature", "sha": "a" * 40}
        with patch("boru.connectors.github.MAX_AUTHORIZATION_REQUESTS", 2):
            for _ in range(2):
                with self.assertRaisesRegex(ConnectorDenied, "reference_head_unavailable"):
                    provider.call(grant, "create_branch", payload, body=body)
            with self.assertRaisesRegex(ConnectorDenied, "authorization_traffic_exhausted"):
                provider.call(grant, "create_branch", payload, body=body)
        self.assertEqual(2, len(calls))

    def test_branch_source_verifies_exact_transmitted_snapshot(self):
        import os
        from unittest.mock import patch
        from boru.connectors.base import Capability
        from boru.connectors.github import GitHubProvider
        from boru.errors import ConnectorDenied
        body = {"ref": "refs/heads/feature", "sha": "b" * 40}
        posts = []
        def transport(method, path, payload):
            if path == "/user":
                body["sha"] = "a" * 40
                return 200, b'{"login":"owner"}'
            if "/git/ref/heads/" in path:
                return 200, ('{"object":{"sha":"' + "a"*40 + '"}}').encode()
            posts.append(payload)
            return 200, b"{}"
        provider = GitHubProvider(token_env="BORU_R6_MOCK_TOKEN", transport=transport)
        grant = self.grant(operations=("create_branch",),
                           capabilities=(Capability.CODE_PR_WRITE,))
        with patch.dict(os.environ, {"BORU_R6_MOCK_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(ConnectorDenied, "reference_not_granted"):
                provider.call(grant, "create_branch", {"repository": "owner/repo"},
                              body=body)
        self.assertEqual([], posts)
