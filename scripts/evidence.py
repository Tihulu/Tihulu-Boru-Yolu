#!/usr/bin/env python3
"""Print a sanitized, reproducible evidence block for this machine (P10 slice).

Runs the repository's own checks and prints what actually happened: the check
set, counts, exit codes and the commit under test. It records no private path,
no device inventory, no credential and no terminal output — only the sanitized
values below, which is exactly what `docs/ACCEPTANCE.md` asks for.

Usage: python3 scripts/evidence.py [--json]
Exit status: 0 when every mandatory check passes, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
CHECKS = [sys.executable, str(ROOT / "scripts" / "check_project.py")]


def _run(argv):
    proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    return proc.returncode, proc.stdout + proc.stderr


def _commit():
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True)
    return proc.stdout.strip() or "unknown"


def _test_count(output: str) -> int:
    for line in output.splitlines():
        if line.startswith("Ran "):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return -1
    return -1


def _install_round_trip() -> dict:
    """Install into a temporary directory, run the demo, then uninstall."""
    root = Path(tempfile.mkdtemp(prefix="boru-evidence-"))
    try:
        os.chmod(root, 0o700)
        target = root / "share"
        state = root / "state"
        bin_dir = root / "bin"
        target.mkdir()
        state.mkdir()
        bin_dir.mkdir()
        os.chmod(state, 0o700)
        installer = subprocess.run(["/bin/sh", str(ROOT / "scripts" / "install_boru.sh"),
                                    "--target", str(target), "--state-dir", str(state),
                                    "--bin-dir", str(bin_dir)], cwd=str(ROOT),
                                   capture_output=True, text=True, timeout=300)
        demo = subprocess.run([sys.executable, "-m", "boru", "demo"], cwd=str(target),
                              capture_output=True, text=True, timeout=300)
        demo_ok = demo.returncode == 0 and '"REVIEW"' in demo.stdout
        uninstaller = subprocess.run(["/bin/sh", str(ROOT / "scripts" / "uninstall_boru.sh"),
                                      "--target", str(target), "--state-dir", str(state),
                                      "--bin-dir", str(bin_dir)], cwd=str(ROOT),
                                     capture_output=True, text=True, timeout=300)
        return {
            "install": "PASS" if installer.returncode == 0 else "FAIL",
            "demo": "PASS" if demo_ok else "FAIL",
            "uninstall": "PASS" if uninstaller.returncode == 0 and not target.exists() else "FAIL",
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def evidence() -> dict:
    check_code, check_out = _run(CHECKS)
    test_code, test_out = _run(TESTS)
    demo_code, demo_out = _run([sys.executable, "-m", "boru", "demo"])
    return {
        "commit": _commit(),
        "python": platform.python_version(),
        "platform": "linux-" + os.uname().machine if hasattr(os, "uname") else "unknown",
        "checks": {
            "static_manifest": "PASS" if check_code == 0 else "FAIL",
            "unit_tests": ("PASS" if test_code == 0 else "FAIL", _test_count(test_out)),
            "offline_demo": "PASS" if demo_code == 0 and '"REVIEW"' in demo_out else "FAIL",
        },
        "install": _install_round_trip(),
        "live_acceptance": "HOLD",
        "note": "MOCK/STATIC evidence only; live gates require owner approval.",
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    payload = evidence()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if "--json" in argv:
        sys.stdout.write(text + "\n")
    else:
        for key, value in payload.items():
            sys.stdout.write("{}: {}\n".format(key, value))
    mandatory = [payload["checks"]["static_manifest"], payload["checks"]["unit_tests"][0],
                 payload["checks"]["offline_demo"]] + list(payload["install"].values())
    return 0 if all(item == "PASS" for item in mandatory) else 1


if __name__ == "__main__":
    raise SystemExit(main())
