"""Review six remediation: actual connector boundaries, mock transport only."""
import json
import time
import unittest
from unittest import mock
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.connectors.polling import EventAllowlist, PollingSync, SyncEvent, MAX_SEEN
from boru.errors import ConnectorDenied


def grant(operation, capability):
    return Grant(grant_id="r6", account="owner", repository="owner/repo",
                 reference="main", operations=(operation,), capabilities=(capability,),
                 max_calls=64, issued_at=time.time(), expires_at=time.time()+600,
                 nonce="r6")


class FlippingMapping(Mapping):
    """First materialization is authoritative; later reads differ."""
    def __init__(self, key, first, later):
        self.key, self.first, self.later = key, first, later
        self.reads = 0
    def __iter__(self):
        return iter((self.key,))
    def __len__(self):
        return 1
    def __getitem__(self, key):
        if key != self.key:
            raise KeyError(key)
        self.reads += 1
        return self.first if self.reads == 1 else self.later


class RequestTests(unittest.TestCase):
    def test_slots_never_re_read_caller_mapping(self):
        for provider_type in (GitHubProvider, GitLabProvider):
            with self.subTest(provider=provider_type.__name__):
                paths = []
                def transport(method, path, body):
                    paths.append(path)
                    return 200, b"{}"
                provider = provider_type(transport=transport)
                payload = FlippingMapping("repository", "owner/repo", "intruder/repo")
                provider.call(grant("list_issues", Capability.REPO_READ), "list_issues", payload)
                self.assertEqual(1, payload.reads)
                self.assertTrue(paths)
                self.assertFalse(any("intruder" in path for path in paths))

    def test_array_wire_shape_and_body_read_once(self):
        for provider_type in (GitHubProvider, GitLabProvider):
            for labels in ([], ["bug"], ["ab"], [["x", "y"]]):
                with self.subTest(provider=provider_type.__name__, labels=labels):
                    received = []
                    def transport(method, path, body):
                        received.append(body)
                        return 200, b"{}"
                    provider = provider_type(transport=transport)
                    body = FlippingMapping("labels", labels, ["changed"])
                    provider.call(grant("create_issue", Capability.ISSUE_WRITE), "create_issue",
                                  {"repository":"owner/repo"}, body=body)
                    self.assertEqual(1, body.reads)
                    self.assertEqual([{"labels":labels}], received)

    def test_branch_authorizes_exact_captured_sha_after_callback(self):
        good, bad = "a"*40, "b"*40
        sent = []
        body = {"ref":"refs/heads/feature", "sha":bad}
        def transport(method, path, payload):
            sent.append((method, path, payload))
            if method == "GET":
                return 200, json.dumps({"object":{"sha":good}}).encode()
            return 200, b"{}"
        provider = GitHubProvider(transport=transport)
        def mutate(*args):
            body["sha"] = good
        with mock.patch.object(provider, "_require_account_identity", side_effect=mutate):
            with self.assertRaisesRegex(ConnectorDenied, "reference_not_granted"):
                provider.call(grant("create_branch", Capability.CODE_PR_WRITE), "create_branch",
                              {"repository":"owner/repo","reference":"main"}, body=body)
        self.assertEqual(["GET"], [method for method, _, _ in sent])

    def test_failed_branch_source_lookups_charge_budget(self):
        sent = []
        def transport(method, path, body):
            sent.append((method,path))
            return 404, b"{}"
        provider = GitHubProvider(transport=transport)
        with mock.patch("boru.connectors.github.MAX_AUTHORIZATION_REQUESTS", 2):
            for _ in range(2):
                with self.assertRaisesRegex(ConnectorDenied, "reference_head_unavailable"):
                    provider.call(grant("create_branch", Capability.CODE_PR_WRITE), "create_branch",
                                  {"repository":"owner/repo"}, body={"ref":"refs/heads/f","sha":"a"*40})
            with self.assertRaisesRegex(ConnectorDenied, "authorization_traffic_exhausted"):
                provider.call(grant("create_branch", Capability.CODE_PR_WRITE), "create_branch",
                              {"repository":"owner/repo"}, body={"ref":"refs/heads/f","sha":"a"*40})
        self.assertEqual(2, len(sent))


class PollingAtomicityTests(unittest.TestCase):
    def test_capacity_failure_preserves_registry_and_retry(self):
        sync = PollingSync(EventAllowlist(["push"]), seen=(str(i) for i in range(MAX_SEEN-1)))
        before = sync.seen
        with self.assertRaisesRegex(ConnectorDenied, "seen_registry_full"):
            sync.accept([SyncEvent("a","push"),SyncEvent("b","push")])
        self.assertEqual(before, sync.seen)
        self.assertEqual(["a"], [e.event_id for e in sync.accept([SyncEvent("a","push")])])

    def test_caller_batch_is_traversed_once(self):
        class Batch:
            def __init__(self):
                self.reads = 0
            def __iter__(self):
                self.reads += 1
                return iter([SyncEvent("a","push")] if self.reads == 1 else [SyncEvent("b","delete")])
        sync = PollingSync(EventAllowlist(["push"]))
        batch = Batch()
        self.assertEqual(["a"], [e.event_id for e in sync.accept(batch)])
        self.assertEqual(1, batch.reads)
        self.assertEqual(("a",), sync.seen)

    def test_concurrent_batches_compete_for_last_slot(self):
        sync = PollingSync(EventAllowlist(["push"]), seen=(str(i) for i in range(MAX_SEEN-1)))
        def submit(identifier):
            try:
                return len(sync.accept([SyncEvent(identifier,"push")]))
            except ConnectorDenied:
                return 0
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ["a","b"]))
        self.assertEqual([0,1], sorted(results))
        self.assertEqual(MAX_SEEN, len(sync.seen))

    def test_malformed_payload_is_not_silently_coerced(self):
        sync = PollingSync(EventAllowlist(["push"]))
        for payload in (None, [], [("key", "value")], "invalid"):
            with self.subTest(payload=payload):
                with self.assertRaises(ConnectorDenied):
                    sync.normalize([{"id":"a","type":"push","payload":payload}])
        self.assertEqual((), sync.seen)

    def test_duplicate_batch_counts_unique_new_ids(self):
        sync = PollingSync(EventAllowlist(["push"]), seen=(str(i) for i in range(MAX_SEEN-1)))
        self.assertEqual(["a"], [e.event_id for e in sync.accept([SyncEvent("a","push"),SyncEvent("a","push")])])
        self.assertEqual(MAX_SEEN, len(sync.seen))


if __name__ == "__main__":
    unittest.main()
