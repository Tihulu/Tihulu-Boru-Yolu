"""Install/rollback slice tests (P10 source slice, not OS acceptance)."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(REPO, "scripts", "install_boru.sh")
UNINSTALL = os.path.join(REPO, "scripts", "uninstall_boru.sh")


class InstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-install-")
        os.chmod(self.root, 0o700)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_script(self, script, args):
        return subprocess.run(["/bin/sh", script] + args, capture_output=True, text=True, timeout=120)

    def paths(self):
        return {
            "target": os.path.join(self.root, "share"),
            "state": os.path.join(self.root, "state"),
            "bin": os.path.join(self.root, "bin"),
        }

    def test_dry_run_creates_nothing(self):
        paths = self.paths()
        result = self.run_script(INSTALL, ["--dry-run", "--target", paths["target"],
                                           "--state-dir", paths["state"], "--bin-dir", paths["bin"]])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(os.path.exists(paths["target"]))
        self.assertFalse(os.path.exists(paths["state"]))
        self.assertFalse(os.path.exists(os.path.join(paths["bin"], "boru")))

    def test_install_then_uninstall_round_trip(self):
        paths = self.paths()
        install = self.run_script(INSTALL, ["--target", paths["target"], "--state-dir", paths["state"],
                                            "--bin-dir", paths["bin"]])
        self.assertEqual(0, install.returncode, install.stderr)
        self.assertTrue(os.path.isfile(os.path.join(paths["target"], "boru", "core.py")))
        self.assertTrue(os.path.isfile(os.path.join(paths["target"], "core.example.json")))
        self.assertTrue(os.path.isfile(os.path.join(paths["bin"], "boru")))
        mode = stat.S_IMODE(os.stat(paths["state"]).st_mode)
        self.assertEqual(0o700, mode)
        # the installed slice runs from the copied directory
        run = subprocess.run([sys_executable(), "-m", "boru", "demo"], cwd=paths["target"],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertIn('"REVIEW"', run.stdout)
        uninstall = self.run_script(UNINSTALL, ["--target", paths["target"], "--state-dir", paths["state"],
                                                "--bin-dir", paths["bin"]])
        self.assertEqual(0, uninstall.returncode, uninstall.stderr)
        self.assertFalse(os.path.exists(paths["target"]))
        self.assertFalse(os.path.exists(paths["state"]))
        self.assertFalse(os.path.exists(os.path.join(paths["bin"], "boru")))

    def test_unknown_option_rejected(self):
        result = self.run_script(INSTALL, ["--nope"])
        self.assertEqual(2, result.returncode)

    def test_installer_never_touches_other_home_paths(self):
        sentinel = os.path.join(self.root, "sensitive")
        os.makedirs(sentinel, exist_ok=True)
        with open(os.path.join(sentinel, "keep.txt"), "w", encoding="utf-8") as handle:
            handle.write("preserve me")
        paths = self.paths()
        self.run_script(INSTALL, ["--target", paths["target"], "--state-dir", paths["state"],
                                  "--bin-dir", paths["bin"]])
        self.assertTrue(os.path.isfile(os.path.join(sentinel, "keep.txt")))

    def test_uninstall_dry_run_keeps_files(self):
        paths = self.paths()
        self.run_script(INSTALL, ["--target", paths["target"], "--state-dir", paths["state"],
                                  "--bin-dir", paths["bin"]])
        self.run_script(UNINSTALL, ["--dry-run", "--target", paths["target"], "--state-dir", paths["state"],
                                    "--bin-dir", paths["bin"]])
        self.assertTrue(os.path.isfile(os.path.join(paths["target"], "boru", "core.py")))


def sys_executable():
    import sys

    return sys.executable


class LauncherAndSafetyTests(unittest.TestCase):
    """The installed launcher works anywhere; the uninstaller refuses harm."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="boru-install2-")
        os.chmod(self.root, 0o700)
        self.paths = {
            "target": os.path.join(self.root, "share"),
            "state": os.path.join(self.root, "state"),
            "bin": os.path.join(self.root, "bin"),
        }

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_script(self, script, args):
        return subprocess.run(["/bin/sh", script] + args, capture_output=True, text=True, timeout=120)

    def install(self, *relative_to_root):
        target = os.path.join(self.root, *relative_to_root) if relative_to_root else self.paths["target"]
        result = self.run_script(INSTALL, ["--target", target, "--state-dir", self.paths["state"],
                                           "--bin-dir", self.paths["bin"]])
        self.assertEqual(0, result.returncode, result.stderr)
        return target

    def test_launcher_works_from_an_unrelated_directory(self):
        self.install()
        launcher = os.path.join(self.paths["bin"], "boru")
        # a relative --target must not bake a relative PYTHONPATH into the launcher
        with open(launcher, "r", encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn('PYTHONPATH="{}'.format(self.paths["target"]), body)
        run = subprocess.run([launcher, "--state-dir", self.paths["state"], "resources"],
                             cwd=self.root, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertIn('"BALANCED"', run.stdout)

    def test_reinstall_replaces_the_tree(self):
        self.install()
        stale = os.path.join(self.paths["target"], "boru", "stale_module.py")
        with open(stale, "w", encoding="utf-8") as handle:
            handle.write("# a module this repository no longer has\n")
        self.install()
        self.assertFalse(os.path.exists(stale), "a re-install must not leave a stale module")

    def test_uninstall_refuses_dangerous_and_relative_targets(self):
        self.install()
        for bad in ("/", os.path.expanduser("~"), "relative/path", "/etc"):
            result = self.run_script(UNINSTALL, ["--target", bad, "--state-dir", self.paths["state"],
                                                 "--bin-dir", self.paths["bin"]])
            self.assertEqual(2, result.returncode, bad)
            self.assertIn("refusing", result.stderr + result.stdout)
        # nothing was removed
        self.assertTrue(os.path.exists(self.paths["target"]))
        self.assertTrue(os.path.exists(self.paths["state"]))

    def test_uninstall_removes_only_the_boru_launcher(self):
        self.install()
        sibling = os.path.join(self.paths["bin"], "other-command")
        with open(sibling, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.run_script(UNINSTALL, ["--target", self.paths["target"], "--state-dir", self.paths["state"],
                                    "--bin-dir", self.paths["bin"]])
        self.assertFalse(os.path.exists(self.paths["target"]))
        self.assertFalse(os.path.exists(self.paths["state"]))
        self.assertFalse(os.path.exists(os.path.join(self.paths["bin"], "boru")))
        self.assertTrue(os.path.isfile(sibling), "an unrelated command must survive")


if __name__ == "__main__":
    unittest.main()
