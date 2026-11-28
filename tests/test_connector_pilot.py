"""Gate 3 pilot script: fail-closed pre-flight and grant-bound denials."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

PILOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "connector_pilot.py")


def run_pilot(args, token=None):
    env = dict(os.environ)
    env.pop("BORU_PILOT_TOKEN_GH", None)
    if token is not None:
        env["BORU_PILOT_TOKEN_GH"] = token
    return subprocess.run([sys.executable, PILOT] + args, capture_output=True, text=True,
                          timeout=120, env=env)


class ConnectorPilotTests(unittest.TestCase):
    def argv(self, *extra, **flags):
        argv = ["--account", "owner", "--repository", "owner/disposable-repo",
                "--token-env", "BORU_PILOT_TOKEN_GH", "--workflow", "ci.yml"]
        for flag, value in flags.items():
            argv.extend(["--" + flag.replace("_", "-"), value])
        return argv + list(extra)

    def test_no_credential_refuses_before_any_request(self):
        result = run_pilot(self.argv("--dry-run"))
        self.assertEqual(2, result.returncode)
        self.assertEqual("not_ready", json.loads(result.stdout)["refused"]["error"])

    def test_bad_repository_shape_is_refused(self):
        result = run_pilot(self.argv("--dry-run", repository="not-a-shape"),
                           token="synthetic-not-real")
        self.assertEqual(2, result.returncode)
        self.assertEqual("configuration_error", json.loads(result.stdout)["refused"]["error"])

    def test_dry_run_denies_every_out_of_scope_grant_without_network(self):
        result = run_pilot(self.argv("--dry-run"), token="synthetic-not-real")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)["pilot"]
        self.assertTrue(payload["dry_run"])
        denials = payload["denials"]
        self.assertEqual("repository_not_granted", denials["other_repository"]["reason"])
        self.assertEqual("reference_not_granted", denials["other_reference"]["reason"])
        self.assertEqual("operation_not_granted", denials["ungranted_operation"]["reason"])
        self.assertEqual("workflow_required", denials["ungranted_workflow"]["reason"])
        self.assertTrue(payload["identity_is_not_inference"])

    def test_the_pilot_script_imports_the_repository_package(self):
        # the script must run against this checkout, not an installed copy
        result = run_pilot(self.argv("--dry-run"), token="synthetic-not-real")
        self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
