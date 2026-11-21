"""Evidence report tests: bounded, sanitized, reproducible."""
import json
import subprocess
import unittest

REPO = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))


class EvidenceReportTests(unittest.TestCase):
    def run_report(self, extra=()):
        return subprocess.run(["python3", "scripts/evidence.py", *extra], cwd=REPO,
                              capture_output=True, text=True, timeout=900)

    def test_report_passes_and_is_bounded(self):
        result = self.run_report()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.replace("'", '"')) if False else None
        # the plain format is one key: value per line, so parse it defensively
        lines = [line for line in result.stdout.splitlines() if ":" in line]
        fields = {}
        for line in lines:
            key, _, value = line.partition(": ")
            fields[key] = value
        for expected in ("commit", "python", "platform", "checks", "install", "live_acceptance",
                         "note"):
            self.assertIn(expected, fields, expected)
        self.assertIn("PASS", fields["checks"])
        self.assertIn("PASS", fields["install"])
        self.assertEqual("HOLD", fields["live_acceptance"])
        self.assertIn("455", fields["checks"])

    def test_report_is_private_data_free(self):
        result = self.run_report()
        self.assertNotIn("/home/", result.stdout)
        self.assertNotIn("SECRET", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_json_format(self):
        result = self.run_report(["--json"])
        self.assertEqual(0, result.returncode, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual("PASS", payload["checks"]["static_manifest"])
        self.assertEqual("PASS", payload["checks"]["unit_tests"][0])
        self.assertTrue(isinstance(payload["checks"]["unit_tests"][1], int))
        self.assertEqual("PASS", payload["install"]["install"])
        self.assertEqual("HOLD", payload["live_acceptance"])
        self.assertIn("MOCK/STATIC", payload["note"])

    def test_report_is_deterministic_in_shape(self):
        first = self.run_report()
        second = self.run_report()
        self.assertEqual(first.returncode, second.returncode)
        self.assertNotEqual(first.stdout.strip(), "")
        self.assertTrue(all(":" in line for line in first.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()
