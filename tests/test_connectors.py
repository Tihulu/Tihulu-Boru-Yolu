"""Repository connector tests: grants bind operations, not prompts."""
import time
import unittest

from boru.connectors.base import (
    OPERATION_CAPABILITIES, WRITE_OPERATIONS, Capability, Grant,
)
from boru.connectors.github import GitHubProvider, read_only_denies
from boru.errors import ConnectorDenied, PolicyViolation


def grant(**overrides):
    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("list_issues",), capabilities=(Capability.REPO_READ,),
                max_calls=3, issued_at=time.time(), expires_at=time.time() + 60, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class GrantTests(unittest.TestCase):
    def test_read_only_grant_refuses_every_write(self):
        subject = grant(operations=("list_issues", "create_issue", "merge_pull", "dispatch_workflow"))
        for operation in WRITE_OPERATIONS:
            if operation in subject.operations:
                allowed, reason = subject.permits(operation, time.time(), 0)
                self.assertFalse(allowed, operation)
                self.assertEqual("capability_not_granted", reason)

    def test_operation_must_be_granted(self):
        allowed, reason = grant().permits("create_issue", time.time(), 0)
        self.assertEqual((False, "operation_not_granted"), (allowed, reason))

    def test_unknown_operation_not_in_matrix(self):
        with self.assertRaises(KeyError):
            OPERATION_CAPABILITIES["nope"]

    def test_call_ceiling_is_enforced(self):
        subject = grant(max_calls=2)
        self.assertTrue(subject.permits("list_issues", time.time(), 1)[0])
        allowed, reason = subject.permits("list_issues", time.time(), 2)
        self.assertEqual((False, "grant_exhausted"), (allowed, reason))

    def test_expiry_is_enforced(self):
        subject = grant(issued_at=time.time() - 10, expires_at=time.time() - 1)
        allowed, reason = subject.permits("list_issues", time.time(), 0)
        self.assertEqual((False, "grant_expired"), (allowed, reason))

    def test_invalid_grants_rejected(self):
        for bad in (
            dict(grant_id=""),
            dict(operations=()),
            dict(capabilities=()),
            dict(max_calls=0),
            dict(max_calls=True),
            dict(expires_at=time.time() - 60),
            dict(disclosure_recipient="x" * 200),
            dict(operations=("not_an_operation",)),
            dict(issued_at="soon"),
        ):
            with self.assertRaises((AssertionError, ValueError)):
                item = grant(**bad)
                errors = item.validate()
                if not errors:
                    raise AssertionError("grant accepted invalid field")
                self.assertTrue(errors)


class GitHubProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = GitHubProvider()
        self.grant = grant()

    def test_default_state_is_disconnected(self):
        self.assertEqual("disconnected", self.provider.connection_state())

    def test_token_env_must_be_a_bounded_name(self):
        for bad in ("", "x" * 100, 5):
            with self.assertRaises(PolicyViolation):
                GitHubProvider(token_env=bad)

    def test_https_required(self):
        with self.assertRaises(PolicyViolation):
            GitHubProvider(base_url="http://api.github.com")
        self.assertEqual("https://api.github.com", GitHubProvider().base_url)

    def test_denied_operation_makes_no_request(self):
        requests = []
        self.provider._transport = lambda method, path, body: requests.append((method, path)) or (200, b"{}")
        for operation in WRITE_OPERATIONS:
            with self.assertRaises(ConnectorDenied):
                self.provider.call(self.grant, operation, {"repository": "owner/repo"})
        self.assertEqual([], requests)

    def test_allowed_read_goes_through_and_is_audited(self):
        seen = []
        self.provider._transport = lambda method, path, body: seen.append((method, path, body)) or (200, b'{"ok":1}')
        payload = self.provider.call(self.grant, "list_issues", {"repository": "owner/repo"})
        self.assertEqual({"ok": 1}, payload)
        self.assertEqual([("GET", "/repos/owner/repo/issues", {})], seen)
        audit = self.provider.audit()
        self.assertEqual(1, len(audit))
        self.assertEqual("allow", audit[0]["decision"])
        self.assertIn("list_issues", audit[0]["operation"])

    def test_call_ceiling_tracks_requests(self):
        self.provider._transport = lambda method, path, body: (200, b'{"ok":1}')
        ceiling = grant(max_calls=1, nonce="ceiling")
        self.provider.call(ceiling, "list_issues", {"repository": "owner/repo"})
        with self.assertRaises(ConnectorDenied):
            self.provider.call(ceiling, "list_issues", {"repository": "owner/repo"})

    def test_write_grant_is_explicit(self):
        subject = grant(operations=("create_issue",), capabilities=(Capability.ISSUE_WRITE,),
                        nonce="n2")
        seen = []
        self.provider._transport = lambda method, path, body: seen.append((method, path, body)) or (201, b'{"number":2}')
        payload = self.provider.call(subject, "create_issue", {"repository": "owner/repo"},
                                     body={"title": "synthetic"})
        self.assertEqual({"number": 2}, payload)
        self.assertEqual("POST", seen[0][0])
        self.assertEqual("/repos/owner/repo/issues", seen[0][1])
        self.assertEqual({"title": "synthetic"}, seen[0][2])

    def test_capability_pair_required(self):
        subject = grant(operations=("create_issue",), capabilities=(Capability.REPO_READ,))
        self.provider._transport = lambda method, path, body: (201, b"{}")
        with self.assertRaises(ConnectorDenied):
            self.provider.call(subject, "create_issue", {"repository": "owner/repo"})

    def test_http_failures_do_not_leak_bodies(self):
        self.provider._transport = lambda method, path, body: (403, b'{"message":"SECRET"}')
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.grant, "list_issues", {"repository": "owner/repo"})
        self.assertEqual("http_403", str(raised.exception))
        self.assertNotIn("SECRET", str(raised.exception))

    def test_invalid_response_rejected(self):
        self.provider._transport = lambda method, path, body: (200, b"not-json")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.grant, "list_issues", {"repository": "owner/repo"})
        self.assertEqual("invalid_response", str(raised.exception))

    def test_workflow_endpoints_are_official(self):
        self.provider._transport = lambda method, path, body: (200, b'{}')
        reader = grant(operations=("list_workflows",), nonce="w1")
        self.provider.call(reader, "list_workflows", {"repository": "owner/repo"})
        self.provider.call(grant(operations=("get_run",), nonce="n3"), "get_run",
                           {"repository": "owner/repo", "run_id": 42})
        dispatch = grant(operations=("dispatch_workflow",), capabilities=(Capability.ACTIONS_DISPATCH,),
                         nonce="n4")
        self.provider.call(dispatch, "dispatch_workflow", {"repository": "owner/repo", "workflow": "ci.yml"},
                           body={"ref": "main"})
        paths = [event["path"] for event in self.provider.audit()]
        self.assertIn("/repos/owner/repo/actions/workflows", paths)
        self.assertIn("/repos/owner/repo/actions/runs/42", paths)
        self.assertIn("/repos/owner/repo/actions/workflows/ci.yml/dispatches", paths)

    def test_read_only_check_lists_writes(self):
        refused = self.provider.read_only_check(["create_issue", "list_issues"])
        self.assertEqual(["create_issue"], refused)


if __name__ == "__main__":
    unittest.main()
