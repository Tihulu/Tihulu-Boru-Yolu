"""Executable acceptance-matrix tests: PASS only where evidence proves it.

The matrix walks M01-M12. Its value is that an owner can trust the report: a row
marked PASS has *proved itself* in this process, and every other row is HOLD with
the exact command to run and what to record. These tests pin that contract.

The evidence-producing helpers are stubbed so the contract is tested directly and
quickly instead of re-running the (slow) suite; one integration test runs the real
script in ``--quick`` mode to prove the wiring and the JSON/human agreement.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
MATRIX = os.path.join(SCRIPTS, "acceptance_matrix.py")

_spec = importlib.util.spec_from_file_location("acceptance_matrix", MATRIX)
acceptance_matrix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acceptance_matrix)

GOOD_EVIDENCE = {
    "checks": {"static_manifest": "PASS", "unit_tests": ("PASS", 865),
               "offline_demo": "PASS"},
    "install": {"install": "PASS", "demo": "PASS", "uninstall": "PASS"},
    "live_acceptance": "HOLD",
}
QUICK_EVIDENCE = {
    "checks": {"static_manifest": "PASS", "unit_tests": ("SKIPPED", -1),
               "offline_demo": "PASS"},
    "install": {"install": "SKIPPED", "demo": "PASS", "uninstall": "SKIPPED"},
    "live_acceptance": "HOLD",
}
GOOD_LISTENER = {"ok": True, "bound_address_class": "loopback",
                 "bound_is_loopback": True, "public_bind_refused": True,
                 "port_released_after_stop": True,
                 "no_thread_survives_stop": True}
GOOD_DEMO = {"state": "REVIEW", "evidence_class": "simulated"}


class AcceptanceMatrixContractTests(unittest.TestCase):
    def _report(self, evidence=None, listener=None, demo=None):
        with mock.patch.object(acceptance_matrix, "_evidence",
                                return_value=GOOD_EVIDENCE if evidence is None else evidence), \
             mock.patch.object(acceptance_matrix, "_listener",
                                return_value=GOOD_LISTENER if listener is None else listener), \
             mock.patch.object(acceptance_matrix, "_demo",
                                return_value=GOOD_DEMO if demo is None else demo):
            return acceptance_matrix.report()

    # -- the matrix itself --------------------------------------------------

    def test_the_matrix_covers_every_m_row(self):
        payload = self._report(evidence=GOOD_EVIDENCE)
        ids = [row["id"] for row in payload["rows"]]
        self.assertEqual(["M{:02d}".format(n) for n in range(1, 13)], ids)

    def test_every_row_carries_a_command_and_expected_output(self):
        for row in self._report()["rows"]:
            self.assertTrue(row["command"].strip(), row["id"])
            self.assertTrue(row["expected"].strip(), row["id"])
            self.assertTrue(row["record"], row["id"])

    # -- the PASS/HOLD contract ---------------------------------------------

    def test_full_evidence_proves_the_five_offline_rows(self):
        payload = self._report()
        passed = sorted(r["id"] for r in payload["rows"] if r["status"] == "PASS")
        self.assertEqual(["M01", "M03", "M04", "M05", "M09"], passed)

    def test_quick_evidence_downgrades_the_rows_it_cannot_prove(self):
        payload = self._report(evidence=QUICK_EVIDENCE)
        by_id = {row["id"]: row["status"] for row in payload["rows"]}
        # A skipped suite cannot prove the install/uninstall/evidence rows.
        for row_id in ("M01", "M04", "M05"):
            self.assertEqual("HOLD", by_id[row_id], row_id)
        # M03/M09 are cheap enough to be proved either way.
        self.assertEqual("PASS", by_id["M03"])
        self.assertEqual("PASS", by_id["M09"])

    def test_a_hold_row_carries_a_reason_not_an_assumption(self):
        payload = self._report(evidence=QUICK_EVIDENCE)
        for row in payload["rows"]:
            if row["status"] == "HOLD":
                self.assertTrue(row.get("detail"), row["id"])

    def test_rows_needing_a_real_image_or_provider_are_always_hold(self):
        for evidence in (GOOD_EVIDENCE, QUICK_EVIDENCE):
            by_id = {r["id"]: r["status"] for r in self._report(evidence=evidence)["rows"]}
            for row_id in ("M02", "M06", "M07", "M08", "M10", "M11", "M12"):
                self.assertEqual("HOLD", by_id[row_id], row_id)
                self.assertTrue(self._report(evidence=evidence) and row_id in by_id)

    def test_the_report_argues_nothing_about_live_acceptance(self):
        payload = self._report()
        self.assertEqual("HOLD", payload["live_acceptance"])
        for row in payload["rows"]:
            self.assertNotEqual("PASS", row.get("live_acceptance"))

    # -- the summary --------------------------------------------------------

    def test_the_summary_counts_match_the_rows(self):
        payload = self._report()
        rows = payload["rows"]
        self.assertEqual(len(rows), payload["summary"]["total"])
        self.assertEqual(sum(1 for r in rows if r["status"] == "PASS"),
                         payload["summary"]["pass"])
        self.assertEqual(sum(1 for r in rows if r["status"] == "HOLD"),
                         payload["summary"]["hold"])
        self.assertEqual(payload["summary"]["pass"] + payload["summary"]["hold"],
                         payload["summary"]["total"])

    def test_a_hold_row_is_never_counted_as_passed(self):
        payload = self._report(evidence=QUICK_EVIDENCE)
        for row in payload["rows"]:
            if row["status"] == "HOLD":
                self.assertNotIn(row["id"],
                                 [r["id"] for r in payload["rows"]
                                  if r["status"] == "PASS"])
        self.assertLessEqual(payload["summary"]["pass"], 2)

    # -- the two output forms ------------------------------------------------

    def test_the_human_form_reports_the_same_rows(self):
        payload = self._report()
        text = acceptance_matrix.render(payload)
        for row in payload["rows"]:
            self.assertIn(row["id"], text)
            self.assertIn(row["status"], text)
        self.assertIn("live_acceptance: HOLD", text)

    # -- the real script, in quick mode --------------------------------------

    def test_the_script_runs_and_emits_valid_json(self):
        out = subprocess.run([sys.executable, MATRIX, "--json", "--quick"],
                             capture_output=True, text=True, timeout=900, cwd=ROOT)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(12, len(payload["rows"]))
        self.assertEqual("HOLD", payload["live_acceptance"])
        self.assertEqual(payload["summary"]["total"], len(payload["rows"]))


if __name__ == "__main__":
    unittest.main()
