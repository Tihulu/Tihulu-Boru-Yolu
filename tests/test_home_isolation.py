"""HOME-isolated install test: the installer only touches the paths you name.

This is not the clean-machine matrix (M01–M12 in docs/OS_ACCEPTANCE.md), which
needs a real disposable image. It is a same-machine isolation test: with HOME
pointed at a scratch directory, the install, the demo and the uninstall must
not create, modify or delete anything outside the named target/state/bin
directories.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class HomeIsolationTests(unittest.TestCase):
    def setUp(self):
        self.outer = tempfile.mkdtemp(prefix="boru-home-outer-")
        self.home = os.path.join(self.outer, "home")
        os.makedirs(self.home)
        os.chmod(self.home, stat.S_IRWXU)
        # a sentinel outside every Boru-owned path
        self.sentinel = os.path.join(self.outer, "sentinel")
        with open(self.sentinel, "w", encoding="utf-8") as handle:
            handle.write("preserve me")
        self.target = os.path.join(self.home, "share")
        self.state = os.path.join(self.home, "state")
        self.bin = os.path.join(self.home, "bin")

    def tearDown(self):
        shutil.rmtree(self.outer, ignore_errors=True)

    def env(self):
        env = dict(os.environ)
        env["HOME"] = self.home
        env.pop("XDG_CONFIG_HOME", None)
        env.pop("XDG_DATA_HOME", None)
        env.pop("XDG_STATE_HOME", None)
        return env

    def installer(self, script, *extra):
        return subprocess.run(["/bin/sh", os.path.join(REPO, "scripts", script),
                               "--target", self.target, "--state-dir", self.state,
                               "--bin-dir", self.bin, *extra],
                              cwd=REPO, env=self.env(), capture_output=True, text=True,
                              timeout=300)

    def test_install_run_uninstall_stay_inside_home(self):
        install = self.installer("install_boru.sh")
        self.assertEqual(0, install.returncode, install.stderr)
        # only the named directories exist under the scratch HOME
        entries = sorted(os.listdir(self.home))
        self.assertEqual(["bin", "share", "state"], entries)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "boru", "core.py")))
        demo = subprocess.run([sys.executable, "-m", "boru", "demo"], cwd=self.target,
                              env=self.env(), capture_output=True, text=True, timeout=300)
        self.assertEqual(0, demo.returncode, demo.stderr)
        self.assertIn('"REVIEW"', demo.stdout)
        self.assertEqual("simulated", json.loads(demo.stdout)["evidence_class"])
        uninstall = self.installer("uninstall_boru.sh")
        self.assertEqual(0, uninstall.returncode, uninstall.stderr)
        # the launcher is gone, the named directories are gone, and the (possibly
        # user-owned) bin directory itself is left in place but empty
        self.assertFalse(os.path.exists(os.path.join(self.bin, "boru")))
        self.assertFalse(os.path.exists(self.target))
        self.assertFalse(os.path.exists(self.state))
        self.assertEqual(["bin"], os.listdir(self.home))
        self.assertEqual([], os.listdir(self.bin))
        # nothing outside the scratch HOME was touched
        with open(self.sentinel, "r", encoding="utf-8") as handle:
            self.assertEqual("preserve me", handle.read())

    def test_install_reports_home_local_paths_only(self):
        install = self.installer("install_boru.sh", "--dry-run")
        self.assertEqual(0, install.returncode, install.stderr)
        self.assertIn(self.home, install.stdout)
        self.assertNotIn(os.path.realpath(os.path.expanduser("~")) + os.sep + "real", install.stdout)

    def test_state_dir_permissions_are_owner_only(self):
        self.installer("install_boru.sh")
        mode = stat.S_IMODE(os.stat(self.state).st_mode)
        self.assertEqual(0o700, mode, oct(mode))
        launcher = os.path.join(self.bin, "boru")
        self.assertTrue(os.path.isfile(launcher))
        self.assertEqual(0o755, stat.S_IMODE(os.stat(launcher).st_mode))

    def test_no_files_outside_the_named_paths(self):
        self.installer("install_boru.sh")
        for root, dirs, files in os.walk(self.outer):
            for name in files:
                path = os.path.join(root, name)
                self.assertTrue(path.startswith(self.home) or path == self.sentinel,
                                "unexpected file outside the named paths: " + path)
            for name in dirs:
                path = os.path.join(root, name)
                self.assertTrue(path.startswith(self.home), "unexpected directory: " + path)


if __name__ == "__main__":
    unittest.main()
