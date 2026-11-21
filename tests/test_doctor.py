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


if __name__ == "__main__":
    unittest.main()
