"""Self-check report tests (P10 helper): sanitized, honest, no host probing."""
import unittest

from boru.doctor import run_checks


class DoctorTests(unittest.TestCase):
    """The report is fast (no suite re-entry) and sanitized."""

    def report(self, state_dir="local-state"):
        return run_checks(state_dir=state_dir, include_tests=False)

    def test_report_is_sanitized_and_honest(self):
        payload = self.report()
        self.assertIn("overall", payload)
        self.assertEqual("HOLD", payload["live_acceptance"])
        self.assertIn("checks", payload)
        for name in ("python", "sqlite", "loopback", "state_dir"):
            self.assertIn(name, payload["checks"])
        text = repr(payload)
        self.assertNotIn("/home/", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("Traceback", text)

    def test_bad_state_directory_fails(self):
        payload = self.report(state_dir=".definitely-missing-dir")
        self.assertEqual("fail", payload["checks"]["state_dir"]["status"])
        self.assertEqual("fail", payload["overall"])

    def test_report_records_only_versions_and_modes(self):
        payload = self.report()
        detail = payload["checks"]["python"].get("detail", "")
        self.assertNotIn("hostname", detail.lower())
        self.assertNotIn("/home", detail)

    def test_group_writable_state_directory_fails(self):
        import os
        import stat
        import tempfile

        root = tempfile.mkdtemp(prefix="boru-doctor-")
        try:
            os.chmod(root, stat.S_IRWXU | stat.S_IWGRP)
            payload = self.report(state_dir=root)
            self.assertEqual("fail", payload["checks"]["state_dir"]["status"])
        finally:
            os.chmod(root, stat.S_IRWXU)
            import shutil

            shutil.rmtree(root, ignore_errors=True)


class OverallPrecedenceTests(unittest.TestCase):
    """A hold must never mask a fail."""

    def test_a_failure_wins_over_a_hold(self):
        import boru.doctor as doctor

        original = doctor._check_state_dir
        doctor._check_state_dir = lambda path: {"status": "fail", "detail": "broken"}
        try:
            payload = doctor.run_checks("local-state", include_tests=False)
        finally:
            doctor._check_state_dir = original
        self.assertEqual("fail", payload["overall"])
        self.assertIn("fail", [c["status"] for c in payload["checks"].values()])

    def test_all_ok_reads_ok(self):
        import boru.doctor as doctor

        payload = doctor.run_checks("local-state", include_tests=False)
        statuses = [c["status"] for c in payload["checks"].values()]
        if "fail" in statuses:
            self.skipTest("this host has a genuinely failing check")
        self.assertIn(payload["overall"], ("ok", "hold"))


if __name__ == "__main__":
    unittest.main()
