"""CLI tests: bounded output, safe errors and explicit review."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args):
    return subprocess.run([sys.executable, "-m", "boru"] + args, cwd=REPO, capture_output=True, text=True,
                          timeout=120)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-cli-")
        os.chmod(self.root, stat.S_IRWXU)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_demo_offline(self):
        result = run(["demo"])
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("REVIEW", payload["state"])
        self.assertEqual("simulated", payload["evidence_class"])
        self.assertEqual("HOLD", payload["live_acceptance"])

    def test_demo_show_text_is_local_only(self):
        result = run(["demo", "--show-text"])
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("text", payload)

    def test_providers_command(self):
        result = run(["providers"])
        self.assertEqual(0, result.returncode, result.stderr)
        providers = json.loads(result.stdout)["providers"]
        self.assertEqual([{"kind": "mock", "models": [], "connection_state": "local"}], providers)

    def test_state_dir_persists_across_invocations(self):
        first = run(["--state-dir", self.root, "demo"])
        self.assertEqual(0, first.returncode, first.stderr)
        second = run(["--state-dir", self.root, "demo"])
        self.assertEqual(1, second.returncode)
        self.assertEqual("store_error", json.loads(second.stdout)["error"])
        self.assertIn("already recorded", json.loads(second.stdout)["detail"])
        status = run(["--state-dir", self.root, "status", "--task-id", "demo-1"])
        self.assertEqual(0, status.returncode, status.stderr)
        self.assertEqual("REVIEW", json.loads(status.stdout)["state"])
        review = run(["--state-dir", self.root, "review", "--task-id", "demo-1", "--accept"])
        self.assertEqual("DONE", json.loads(review.stdout)["state"])
        mode = stat.S_IMODE(os.stat(os.path.join(self.root, "boru-state.sqlite")).st_mode)
        self.assertEqual(0, mode & (stat.S_IRWXG | stat.S_IRWXO))

    def test_run_with_task_file(self):
        task = os.path.join(self.root, "task.json")
        with open(task, "w", encoding="utf-8") as handle:
            json.dump({"task_id": "cli-1", "goal": "synthetic"}, handle)
        result = run(["--state-dir", self.root, "run", "--task", task])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("REVIEW", json.loads(result.stdout)["state"])

    def test_run_rejects_malformed_task_without_traceback(self):
        task = os.path.join(self.root, "task.json")
        with open(task, "w", encoding="utf-8") as handle:
            handle.write("not json")
        result = run(["--state-dir", self.root, "run", "--task", task])
        self.assertEqual(2, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual("configuration_error", json.loads(result.stdout)["error"])

    def test_run_rejects_unknown_task_fields(self):
        task = os.path.join(self.root, "task.json")
        with open(task, "w", encoding="utf-8") as handle:
            json.dump({"task_id": "x", "goal": "g", "environment": "HOME"}, handle)
        result = run(["--state-dir", self.root, "run", "--task", task])
        self.assertIn(result.returncode, (1, 2))
        self.assertNotIn("Traceback", result.stderr)

    def test_state_dir_must_exist(self):
        result = run(["--state-dir", os.path.join(self.root, "absent"), "demo"])
        self.assertEqual(2, result.returncode)
        self.assertEqual("configuration_error", json.loads(result.stdout)["error"])

    def test_cancel_command(self):
        run(["--state-dir", self.root, "demo"])
        result = run(["--state-dir", self.root, "cancel", "--task-id", "demo-1"])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("CANCELLED", json.loads(result.stdout)["state"])

    def test_help_is_available(self):
        result = run(["--help"])
        self.assertEqual(0, result.returncode)
        self.assertIn("demo", result.stdout)


class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-cfg-")
        os.chmod(self.root, stat.S_IRWXU)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_example_config_runs(self):
        example = os.path.join(REPO, "examples", "core.example.json")
        result = run(["--config", example, "demo"])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("REVIEW", json.loads(result.stdout)["state"])

    def test_bad_config_is_rejected_safely(self):
        path = os.path.join(self.root, "bad.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"providers": [{"kind": "jan", "endpoint": "http://example.com/v1", "local_model_ids": ["m"]}]}')
        result = run(["--config", path, "demo"])
        self.assertEqual(2, result.returncode)
        self.assertEqual("configuration_error", json.loads(result.stdout)["error"])
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()


class AuditCommandTests(unittest.TestCase):
    """`boru audit` prints bounded ledger rows and never leaks a path."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-audit-cli-")
        os.chmod(self.root, stat.S_IRWXU)
        self.audit_dir = os.path.join(self.root, "audit")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_audit_requires_a_directory(self):
        result = run(["audit"])
        self.assertEqual(2, result.returncode)
        self.assertEqual("configuration_error", json.loads(result.stdout)["error"])

    def test_audit_prints_rows(self):
        from boru.audit import RejectionLedger

        os.makedirs(self.audit_dir)
        os.chmod(self.audit_dir, stat.S_IRWXU)
        with RejectionLedger(self.audit_dir) as ledger:
            ledger.record("policy", "task-1", "task_axes_refused", "policy")
            ledger.record("broker", "task-1", "resource_not_declared", "read_file_alias")
        result = run(["audit", "--audit-dir", self.audit_dir, "--limit", "1"])
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("broker", payload["rejections"][0]["category"])
        self.assertEqual("HOLD", payload["live_acceptance"])
        self.assertNotIn(self.root, result.stdout)

    def test_audit_rejects_a_missing_directory(self):
        result = run(["audit", "--audit-dir", os.path.join(self.root, "absent")])
        self.assertEqual(2, result.returncode)
        self.assertEqual("configuration_error", json.loads(result.stdout)["error"])

    def test_audit_rejects_a_bad_limit(self):
        os.makedirs(self.audit_dir)
        os.chmod(self.audit_dir, stat.S_IRWXU)
        result = run(["audit", "--audit-dir", self.audit_dir, "--limit", "not-a-number"])
        self.assertEqual(2, result.returncode)
        self.assertIn("limit", json.loads(result.stdout)["detail"])

    def test_audit_is_listed_in_help(self):
        result = run(["--help"])
        self.assertEqual(0, result.returncode)
        self.assertIn("audit", result.stdout)
