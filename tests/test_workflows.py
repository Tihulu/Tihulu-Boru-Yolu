"""Workflow discovery and dispatch-input validation tests (issue #9)."""
import unittest

from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.workflows import (
    INPUT_TYPES, WorkflowSummary, parse_workflows, validate_dispatch_inputs,
)
from boru.errors import ConnectorDenied


def grant(**overrides):
    import time

    base = dict(grant_id="g1", account="owner", repository="owner/repo", reference="main",
                operations=("list_workflows",), capabilities=(Capability.REPO_READ,),
                max_calls=3, issued_at=time.time(), expires_at=time.time() + 60, nonce="n1")
    base.update(overrides)
    return Grant(**base)


class ParseTests(unittest.TestCase):
    def test_parses_official_shape(self):
        parsed = parse_workflows({"total_count": 1, "workflows": [
            {"id": 7, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active",
             "supports_dispatch": True}]})
        self.assertEqual(1, len(parsed))
        self.assertEqual(("7", "CI", ".github/workflows/ci.yml", "active", True),
                         (parsed[0].workflow_id, parsed[0].name, parsed[0].path,
                          parsed[0].state, parsed[0].supports_dispatch))

    def test_bad_payloads_are_refused(self):
        for bad in ([], "nope", {"workflows": "x"}, {"workflows": [1]},
                    {"workflows": [{"name": "x", "path": "y"}]}):
            with self.assertRaises(ConnectorDenied):
                parse_workflows(bad)

    def test_summary_validation(self):
        self.assertTrue(WorkflowSummary(workflow_id="", name="n", path="p").validate())
        self.assertTrue(WorkflowSummary(workflow_id="1", name="n", path="p",
                                       supports_dispatch="yes").validate())


class InputValidationTests(unittest.TestCase):
    def declared(self):
        return {
            "ref": {"type": "string", "required": True},
            "verbose": {"type": "boolean"},
            "mode": {"type": "choice", "options": ["fast", "slow"]},
            "jobs": {"type": "number", "minimum": 1, "maximum": 8},
        }

    def test_valid_inputs_pass(self):
        ok, reason = validate_dispatch_inputs(self.declared(),
                                              {"ref": "main", "verbose": True,
                                               "mode": "fast", "jobs": 2})
        self.assertEqual((True, ""), (ok, reason))

    def test_invalid_inputs_are_refused(self):
        cases = (
            ({"ref": "main", "nope": "x"}, "input_not_declared"),
            ({"ref": "main", "verbose": "yes"}, "input_type_mismatch"),
            ({"ref": "main", "mode": "other"}, "input_out_of_range"),
            ({"ref": "main", "jobs": 99}, "input_out_of_range"),
            ({"ref": "main", "jobs": 0}, "input_out_of_range"),
            ({}, "required_input_missing"),
            ({"ref": "x" * 600}, "inputs_malformed"),
        )
        for provided, reason in cases:
            self.assertEqual((False, reason),
                             validate_dispatch_inputs(self.declared(), provided), provided)

    def test_oversized_and_nested_inputs_refused(self):
        many = {"f{}".format(i): "x" for i in range(20)}
        self.assertEqual((False, "inputs_too_many"),
                         validate_dispatch_inputs(self.declared(), many))
        self.assertEqual((False, "inputs_malformed"),
                         validate_dispatch_inputs(self.declared(), {"ref": {"nested": "y"}}))
        self.assertEqual((False, "inputs_malformed"),
                         validate_dispatch_inputs(self.declared(), {"ref": "line\nbreak"}))

    def test_undeclared_workflow_refuses(self):
        self.assertEqual((False, "inputs_undeclared"),
                         validate_dispatch_inputs(None, {"ref": "main"}))

    def test_known_input_types(self):
        self.assertEqual(("string", "boolean", "choice", "number", "environment"), INPUT_TYPES)


class ProviderDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider = GitHubProvider()
        self.grant = grant(nonce="wf-1")
        self.requests = []
        self.provider._transport = lambda method, path, body: self.requests.append(
            (method, path)) or (200, b'{"workflows": [{"id": 1, "name": "CI", "path": "p", '
                                              b'"state": "active", "supports_dispatch": true}]}')

    def test_discovery_uses_the_official_path(self):
        parsed = self.provider.list_workflows_typed(self.grant, {"repository": "owner/repo"})
        self.assertEqual(["1"], [w.workflow_id for w in parsed])
        self.assertEqual([("GET", "/repos/owner/repo/actions/workflows")], self.requests)

    def test_discovery_requires_a_grant(self):
        denied = grant(operations=("list_issues",), nonce="wf-2")
        with self.assertRaises(ConnectorDenied):
            self.provider.list_workflows_typed(denied, {"repository": "owner/repo"})
        self.assertEqual([], self.requests)

    def test_other_repository_is_refused(self):
        with self.assertRaises(ConnectorDenied):
            self.provider.list_workflows_typed(self.grant, {"repository": "other/repo"})
        self.assertEqual([], self.requests)

    def test_bad_response_is_refused(self):
        self.provider._transport = lambda method, path, body: (200, b"not json")
        with self.assertRaises(ConnectorDenied):
            self.provider.list_workflows_typed(self.grant, {"repository": "owner/repo"})


if __name__ == "__main__":
    unittest.main()
