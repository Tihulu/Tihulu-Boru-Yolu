"""The Gate 1 review package must stay true as the repository changes.

A package a reviewer relies on cannot cite tests, paths or counts that no
longer exist: every test name and file path it names must exist, and every
count it states must match the manifest.  The check is static so it does not
double the suite's runtime.
"""
import importlib.util
import os
import re
import unittest

PACKAGE = "docs/REVIEW_PACKAGE.md"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _manifest_size() -> int:
    spec = importlib.util.spec_from_file_location(
        "check_project", os.path.join(ROOT, "scripts", "check_project.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return len(module.REQUIRED_DOCS)


def _defined_tests() -> set:
    defined = set()
    tests_dir = os.path.join(ROOT, "tests")
    for name in sorted(os.listdir(tests_dir)):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(tests_dir, name), "r", encoding="utf-8") as handle:
                defined.update(re.findall(r"def (test_[a-z0-9_]+)", handle.read()))
    return defined


class ReviewPackageTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, PACKAGE), "r", encoding="utf-8") as handle:
            self.text = handle.read()

    def test_every_cited_test_exists_in_the_suite(self):
        cited = set(re.findall(r"`(test_[a-z0-9_]+)`", self.text))
        defined = _defined_tests()
        missing = sorted(name for name in cited if name not in defined)
        self.assertEqual([], missing,
                         "the package cites tests that do not exist: " + ", ".join(missing))

    def test_every_cited_path_exists(self):
        cited = set(re.findall(r"`((?:boru|tests|scripts|docs)/[\w/.-]+\.(?:py|md))`", self.text))
        missing = [name for name in sorted(cited)
                   if not os.path.exists(os.path.join(ROOT, name))]
        self.assertEqual([], missing,
                         "the package cites paths that do not exist: " + ", ".join(missing))

    def test_the_stated_document_count_matches_the_manifest(self):
        match = re.search(r"check_project\.py.*?PASS \((\d+) documents", self.text)
        self.assertIsNotNone(match, "the package states no document count")
        self.assertEqual(_manifest_size(), int(match.group(1)),
                         "the package states a document count that no longer matches")

    def test_the_package_records_a_head_commit(self):
        self.assertRegex(self.text, r"head under review: `[0-9a-f]{40}`")

    def test_the_package_does_not_claim_a_verdict(self):
        # a Gate 1 verdict belongs to the reviewer, never to this repository
        self.assertIn("HOLD", self.text)
        self.assertNotIn("Current status: PASS", self.text)


if __name__ == "__main__":
    unittest.main()
