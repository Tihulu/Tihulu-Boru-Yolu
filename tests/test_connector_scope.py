"""P8 request-scope regression tests — no live network or credentials."""
import time
import unittest

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.errors import ConnectorDenied


def scoped_grant(repository, operations=("list_issues",), capabilities=(Capability.REPO_READ,)):
    now = time.time()
    return Grant(
        grant_id="scope-test", account="owner", repository=repository,
        reference="main", operations=operations, capabilities=capabilities,
        max_calls=2, issued_at=now, expires_at=now + 300, nonce="scope-nonce",
    )


class ConnectorScopeTests(unittest.TestCase):
    def exercise(self, provider_type, repository):
        requests = []
        provider = provider_type(
            transport=lambda method, path, body: (
                requests.append((method, path, body)) or (200, b'{}')
            )
        )
        grant = scoped_grant(repository)
        return provider, grant, requests

    def test_cross_repository_read_is_denied_without_network(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            with self.subTest(provider=provider_type.__name__):
                provider, grant, requests = self.exercise(provider_type, repository)
                with self.assertRaisesRegex(ConnectorDenied, "repository_not_granted"):
                    provider.call(grant, "list_issues", {"repository": "attacker/other"})
                self.assertEqual([], requests)

    def test_method_override_can_never_turn_read_into_write(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            for method in ("DELETE", "POST", "GET"):
                with self.subTest(provider=provider_type.__name__, method=method):
                    with self.assertRaisesRegex(ConnectorDenied, "custom_request_forbidden"):
                        provider.call(grant, "list_issues", {"repository": repository},
                                      method=method)
            self.assertEqual([], requests)

    def test_path_override_is_denied_without_network(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            with self.assertRaisesRegex(ConnectorDenied, "custom_request_forbidden"):
                provider.call(grant, "list_issues", {"repository": repository},
                              path="/admin/organizations")
            self.assertEqual([], requests)

    def test_cross_reference_requests_are_denied_without_network(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            for params, body in (
                ({"repository": repository, "branch": "develop"}, None),
                ({"repository": repository, "ref": "develop"}, None),
                ({"repository": repository}, {"ref": "develop"}),
                ({"repository": repository}, {"repository": "attacker/other"}),
            ):
                with self.subTest(provider=provider_type.__name__, params=params, body=body):
                    with self.assertRaises(ConnectorDenied):
                        provider.call(grant, "list_issues", params, body=body)
            self.assertEqual([], requests)

    def test_read_file_requires_explicit_bound_branch(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            with self.assertRaisesRegex(ConnectorDenied, "reference_required"):
                provider.call(
                    scoped_grant(repository, ("read_file",)),
                    "read_file", {"repository": repository, "path": "docs/README.md"},
                )
            self.assertEqual([], requests)

    def test_unsafe_url_slots_fail_closed(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            reader = scoped_grant(repository, ("get_run",))
            for bad in ("42?admin=true", "42#fragment", "../other", "42%2F7", "42\\x"):
                with self.subTest(provider=provider_type.__name__, bad=bad):
                    with self.assertRaisesRegex(ConnectorDenied, "invalid_parameter"):
                        provider.call(reader, "get_run",
                                      {"repository": repository, "run_id": bad})
            self.assertEqual([], requests)

    def test_malformed_payload_body_are_rejected(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            for invalid_payload, invalid_body in (
                (["not-a-mapping"], None),
                ({"repository": repository}, ["not-a-mapping"]),
            ):
                with self.assertRaisesRegex(ConnectorDenied, "invalid_payload"):
                    provider.call(grant, "list_issues", invalid_payload, body=invalid_body)
            self.assertEqual([], requests)

    def test_denials_do_not_consume_a_permitted_call(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, grant, requests = self.exercise(provider_type, repository)
            with self.assertRaises(ConnectorDenied):
                provider.call(grant, "list_issues", {"repository": "attacker/other"})
            self.assertEqual({}, provider.call(grant, "list_issues",
                                               {"repository": repository}))
            self.assertEqual(1, len(requests))
            self.assertEqual("GET", requests[0][0])

    def test_rejected_query_in_identifier_cannot_escape_endpoint(self):
        for provider_type, repository in (
            (GitHubProvider, "owner/repo"),
            (GitLabProvider, "group/project"),
        ):
            provider, _grant, requests = self.exercise(provider_type, repository)
            writer = scoped_grant(repository, ("comment_issue",),
                                  (Capability.ISSUE_WRITE,))
            with self.assertRaisesRegex(ConnectorDenied, "invalid_parameter"):
                provider.call(writer, "comment_issue",
                              {"repository": repository, "issue": "1?token=unsafe"},
                              body={"body": "test"})
            self.assertEqual([], requests)

    def test_allowed_gitlab_subgroup_remains_typed(self):
        provider, grant, requests = self.exercise(GitLabProvider, "team/sub/project")
        self.assertEqual({}, provider.call(
            grant, "list_issues", {"repository": "team/sub/project"}
        ))
        self.assertEqual("/api/v4/projects/team%2Fsub%2Fproject/issues?per_page=100",
                         requests[0][1])


if __name__ == "__main__":
    unittest.main()
