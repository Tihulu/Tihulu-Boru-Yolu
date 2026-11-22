"""Connector request-scope tests (issue #15): binding, overrides, zero requests."""
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.scope import ACCOUNT_SCOPED, REPO_SCOPED, check_call, repository_matches
from boru.errors import ConnectorDenied


def grant(**overrides):
    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("read_file",), capabilities=(Capability.REPO_READ,),
                max_calls=3, issued_at=time.time(), expires_at=time.time() + 60, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class ScopeUnitTests(unittest.TestCase):
    def test_operation_sets_are_explicit(self):
        self.assertIn("read_file", REPO_SCOPED)
        self.assertIn("create_pull", REPO_SCOPED)
        self.assertEqual({"list_repositories"}, ACCOUNT_SCOPED)

    def test_repository_comparison(self):
        self.assertTrue(repository_matches("owner/repo", "owner/repo"))
        self.assertTrue(repository_matches("owner%2Frepo", "owner/repo"))
        self.assertFalse(repository_matches("other/repo", "owner/repo"))

    def test_bad_slots_are_refused(self):
        for bad in ("", " ", "owner/repo/", "owner//repo", "owner/../repo", "own er/repo",
                    "owner/repo%2fsecret", "owner/repo?x=1", "owner/repo#frag", "owner\\repo",
                    "owner/repo\n"):
            with self.assertRaises(ConnectorDenied):
                check_call(grant(), "read_file", {"repository": bad, "reference": "main"},
                           method=None, path=None, default_method="GET")

    def test_reference_must_match_the_grant(self):
        payload = {"repository": "owner/repo", "reference": "develop"}
        with self.assertRaises(ConnectorDenied) as raised:
            check_call(grant(), "read_file", payload, method=None, path=None, default_method="GET")
        self.assertEqual("reference_not_granted", str(raised.exception))

    def test_missing_reference_is_refused_for_file_reads(self):
        with self.assertRaises(ConnectorDenied) as raised:
            check_call(grant(), "read_file", {"repository": "owner/repo"}, method=None,
                       path=None, default_method="GET")
        self.assertEqual("reference_required", str(raised.exception))

    def test_account_scoped_operation_is_refused_with_a_repository_grant(self):
        with self.assertRaises(ConnectorDenied) as raised:
            check_call(grant(), "list_repositories", {}, method=None, path=None, default_method="GET")
        self.assertEqual("account_scope_not_granted", str(raised.exception))

    def test_unknown_operation_is_refused(self):
        with self.assertRaises(ConnectorDenied) as raised:
            check_call(grant(), "host_shell", {"repository": "owner/repo"}, method=None,
                       path=None, default_method="GET")
        self.assertEqual("operation_not_scoped", str(raised.exception))

    def test_grant_construction_rejects_bad_fields(self):
        # a malformed grant never exists in the first place
        for bad_kwargs in (dict(repository=""), dict(reference=""), dict(repository="a" * 400)):
            with self.assertRaises(ValueError):
                grant(**bad_kwargs)
        payload = {"repository": "owner/repo", "reference": "main"}
        check_call(grant(), "read_file", payload, method=None, path=None, default_method="GET")


class ProviderScopeTests(unittest.TestCase):
    def setUp(self):
        self.provider = GitHubProvider()
        self.grant = grant(nonce="scope-1")
        self.requests = []
        self.provider._transport = lambda method, path, body: self.requests.append(
            (method, path)) or (200, b'{}')

    def body(self, **overrides):
        base = {"repository": "owner/repo", "reference": "main", "branch": "main"}
        base.update(overrides)
        return base

    def test_granted_read_reaches_the_official_path(self):
        item = grant(operations=("read_file",), nonce="scope-2")
        payload = self.body(path="docs/readme.md")
        self.provider.call(item, "read_file", payload)
        self.assertEqual([("GET", "/repos/owner/repo/contents/docs/readme.md?ref=main")], self.requests)

    def test_other_repository_is_refused_without_a_request(self):
        item = grant(operations=("list_issues",), nonce="scope-3")
        with self.assertRaises(ConnectorDenied):
            self.provider.call(item, "list_issues", {"repository": "other/repo"})
        self.assertEqual([], self.requests)

    def test_other_reference_is_refused_without_a_request(self):
        item = grant(reference="main", operations=("list_issues",), nonce="scope-4")
        with self.assertRaises(ConnectorDenied):
            self.provider.call(item, "list_issues",
                               {"repository": "owner/repo", "reference": "develop"})
        self.assertEqual([], self.requests)

    def test_path_override_is_refused(self):
        item = grant(operations=("list_issues",), nonce="scope-5")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(item, "list_issues", {"repository": "owner/repo"},
                               path="/repos/other/repo/secrets")
        self.assertEqual("path_override_refused", str(raised.exception))
        self.assertEqual([], self.requests)

    def test_method_override_is_refused(self):
        item = grant(operations=("list_issues",), nonce="scope-6")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(item, "list_issues", {"repository": "owner/repo"}, method="DELETE")
        self.assertEqual("method_override_refused", str(raised.exception))
        self.assertEqual([], self.requests)

    def test_account_wide_listing_is_refused_with_a_repository_grant(self):
        item = grant(operations=("list_repositories",), nonce="scope-7")
        with self.assertRaises(ConnectorDenied):
            self.provider.call(item, "list_repositories", {})
        self.assertEqual([], self.requests)

    def test_bad_issue_and_workflow_inputs_are_refused(self):
        for payload in ({"repository": "owner/repo", "issue": "../etc"},
                        {"repository": "owner/repo", "issue": "abc"},
                        {"repository": "owner/repo", "workflow": "../ci.yml"},
                        {"repository": "owner/repo", "run_id": "abc"},
                        {"repository": "owner/repo", "sha": "../abc"}):
            item = grant(operations=("get_pull",), nonce="scope-8")
            with self.assertRaises(ConnectorDenied):
                self.provider.call(item, "get_pull", payload)
        self.assertEqual([], self.requests)

    def test_grant_with_unknown_operation_never_exists(self):
        # Grant construction refuses an operation that is not in the matrix.
        with self.assertRaises(ValueError):
            grant(operations=("not_an_operation",), nonce="scope-9")
        self.assertEqual([], self.requests)


    def test_dispatch_body_validates_against_an_owner_declaration(self):
        from boru.connectors.scope import check_dispatch_body

        subject = grant(operations=("dispatch_workflow",),
                         capabilities=(Capability.ACTIONS_DISPATCH,),
                         workflow_ids=("ci.yml",))
        declared = {"target": {"type": "string", "required": True}}
        # a matching body passes; a wrong type or an unknown key is refused
        check_dispatch_body(subject, {"ref": "main", "inputs": {"target": "staging"}}, declared)
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {"target": 5}}, declared)
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {"other": "x"}}, declared)
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {}}, declared)
        # the declaration is owner-provided: a body cannot carry its own schema
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {"target": "staging"},
                                          "declared": {"target": {"type": "string"}}},
                                {"target": {"type": "string", "required": True}})

    def test_owner_declared_schema_travels_with_the_grant(self):
        import json

        from boru.connectors.scope import check_dispatch_body

        schema = json.dumps({"target": {"type": "string", "required": True}})
        subject = grant(operations=("dispatch_workflow",),
                        capabilities=(Capability.ACTIONS_DISPATCH,),
                        workflow_ids=("ci.yml",), input_declaration_json=schema)
        check_dispatch_body(subject, {"ref": "main", "inputs": {"target": "staging"}})
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {"target": 7}})
        with self.assertRaises(ConnectorDenied):
            check_dispatch_body(subject, {"ref": "main", "inputs": {}})
        # a malformed or oversized declaration is refused at grant construction
        for bad in ("not json", json.dumps({"x": {"type": "nope"}}),
                    json.dumps({str(i): {"type": "string"} for i in range(20)})):
            with self.assertRaises(ValueError):
                grant(input_declaration_json=bad)


if __name__ == "__main__":
    unittest.main()


class WorkflowAndEncodingTests(unittest.TestCase):
    """Workflow binding (issue #15) and typed repository encoding."""

    def setUp(self):
        self.provider = GitHubProvider()
        self.requests = []
        self.provider._transport = lambda method, path, body: self.requests.append(
            (method, path)) or (200, b'{}')

    def payload(self, **overrides):
        base = {"repository": "owner/repo", "reference": "main"}
        base.update(overrides)
        return base

    def test_undeclared_workflow_is_denied_without_a_request(self):
        item = grant(operations=("dispatch_workflow",), capabilities=(
            __import__("boru.connectors.base", fromlist=["Capability"]).Capability.ACTIONS_DISPATCH,),
            nonce="wf-1")
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(item, "dispatch_workflow", self.payload(workflow="ci.yml"),
                               body={"ref": "main"})
        self.assertEqual("workflow_not_granted", str(raised.exception))
        self.assertEqual([], self.requests)

    def test_declared_workflow_is_allowed(self):
        item = grant(operations=("dispatch_workflow",), capabilities=(
            __import__("boru.connectors.base", fromlist=["Capability"]).Capability.ACTIONS_DISPATCH,),
            nonce="wf-2", workflow_ids=("ci.yml",))
        self.provider.call(item, "dispatch_workflow", self.payload(workflow="ci.yml"),
                           body={"ref": "main"})
        self.assertEqual([("POST", "/repos/owner/repo/actions/workflows/ci.yml/dispatches")],
                         self.requests)

    def test_bad_workflow_ids_in_a_grant_are_refused(self):
        for bad in (("",), ("ci.yml", "ci.yml"), ("x" * 300,), ("../evil",)):
            with self.assertRaises(ValueError):
                grant(operations=("dispatch_workflow",), nonce="wf-3", workflow_ids=bad)

    def test_repository_ref_encoding(self):
        from boru.connectors.scope import RepositoryRef

        ref = RepositoryRef.parse("owner/repo")
        self.assertEqual("owner/repo", str(ref))
        self.assertEqual("owner/repo", ref.encoded())
        self.assertEqual("owner%2Frepo", ref.percent_encoded())
        for bad in ("", "owner", "owner/repo/extra", "owner//repo", "../etc", "owner/repo%00",
                    "owner/repo?x=1", "owner/repo#f"):
            with self.assertRaises(ConnectorDenied):
                RepositoryRef.parse(bad)

    def test_typed_encoding_is_used_for_the_path(self):
        item = grant(operations=("list_issues",), nonce="wf-4")
        self.provider.call(item, "list_issues", self.payload())
        self.assertEqual([("GET", "/repos/owner/repo/issues")], self.requests)


class _Transport(BaseHTTPRequestHandler):
    """Test-owned endpoint that can answer with a redirect or bad content type."""

    mode = "redirect"
    paths = []

    def log_message(self, *args):
        return

    def do_GET(self):
        type(self).paths.append(self.path)
        if type(self).mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/evil")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"<html>secret</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TransportHardeningTests(unittest.TestCase):
    """Redirects, content types and response references (issue #15 gaps)."""

    def setUp(self):
        _Transport.mode = "redirect"
        _Transport.paths = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Transport)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.provider = GitHubProvider(
            base_url="http://127.0.0.1:{}/".format(self.server.server_address[1]),
            transport=None, allow_http=True)
        self.grant = grant(operations=("read_file",), nonce="th-1")
        self.payload = {"repository": "owner/repo", "reference": "main", "path": "docs/readme.md"}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_redirect_is_refused_and_never_followed(self):
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.grant, "read_file", self.payload)
        self.assertEqual("redirects_not_followed", str(raised.exception))
        self.assertNotIn("evil", str(_Transport.paths))

    def test_unexpected_content_type_is_refused(self):
        _Transport.mode = "html"
        with self.assertRaises(ConnectorDenied) as raised:
            self.provider.call(self.grant, "read_file", self.payload)
        self.assertEqual("unexpected_content_type", str(raised.exception))

    def test_response_reference_mismatch_is_denied(self):
        body = json.dumps({"path": "docs/readme.md", "ref": "develop"}).encode()
        with self.assertRaises(ConnectorDenied) as raised:
            GitHubProvider._verify_response("read_file", self.payload, body)
        self.assertEqual("reference_mismatch", str(raised.exception))
        GitHubProvider._verify_response("read_file", self.payload,
                                       json.dumps({"ref": "main"}).encode())

    def test_other_operations_are_not_reference_verified(self):
        GitHubProvider._verify_response("list_issues", {"repository": "owner/repo"},
                                       json.dumps({"ref": "whatever"}).encode())


if __name__ == "__main__":
    unittest.main()


class IdentityVerificationTests(unittest.TestCase):
    """A token proves an identity, never write or Shell authorization."""

    def setUp(self):
        os.environ["BORU_TEST_GH_TOKEN"] = "not-a-real-token"
        self.provider = GitHubProvider(token_env="BORU_TEST_GH_TOKEN")
        self.grant = grant(operations=("list_issues",), account="owner", nonce="id-1")

    def tearDown(self):
        os.environ.pop("BORU_TEST_GH_TOKEN", None)

    def test_matching_identity_is_authenticated(self):
        self.provider._transport = lambda method, path, body: (200, b'{"login": "owner"}')
        self.assertEqual((True, "authenticated"),
                         self.provider.verify_identity(self.grant.account, timeout=5))

    def test_mismatched_identity_is_refused(self):
        self.provider._transport = lambda method, path, body: (200, b'{"login": "attacker"}')
        self.assertEqual((False, "identity_mismatch"),
                         self.provider.verify_identity(self.grant.account, timeout=5))

    def test_missing_token_is_only_configured(self):
        os.environ.pop("BORU_TEST_GH_TOKEN", None)
        self.assertEqual((False, "configured"),
                         self.provider.verify_identity(self.grant.account, timeout=5))

    def test_bad_grant_account_is_refused(self):
        self.provider._transport = lambda method, path, body: (200, b'{"login": "owner"}')
        self.assertEqual((False, "grant_account_invalid"),
                         self.provider.verify_identity("", timeout=5))

    def test_invalid_identity_response_is_refused(self):
        self.provider._transport = lambda method, path, body: (200, b'{"login": ""}')
        self.assertEqual((False, "identity_endpoint_refused"),
                         self.provider.verify_identity(self.grant.account, timeout=5))

    def test_gitlab_identity_uses_username(self):
        from boru.connectors.gitlab import GitLabProvider

        os.environ["BORU_TEST_GL_TOKEN"] = "not-a-real-token"
        provider = GitLabProvider(token_env="BORU_TEST_GL_TOKEN")
        provider._transport = lambda method, path, body: (200, b'{"username": "owner"}')
        self.assertEqual((True, "authenticated"), provider.verify_identity("owner", timeout=5))
        provider._transport = lambda method, path, body: (200, b'{"username": "other"}')
        self.assertEqual((False, "identity_mismatch"), provider.verify_identity("owner", timeout=5))
        os.environ.pop("BORU_TEST_GL_TOKEN", None)
