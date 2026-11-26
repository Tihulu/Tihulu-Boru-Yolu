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
