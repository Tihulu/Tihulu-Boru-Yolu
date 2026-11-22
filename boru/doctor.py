"""Local self-check for acceptance runs (P10 helper, not a security check).

``boru doctor`` prints a sanitized status of the things an acceptance run needs
to know *before* starting: Python version, whether the repository checks pass,
whether a state directory is usable, and whether the loopback transport can
bind. It never reads Jan/OpenCode configuration, never opens a public listener
and never sends anything anywhere.
"""
from __future__ import annotations

import os
import platform
import socket
import sqlite3
import stat
import sys
from typing import Any, Dict, List

STATUS_ORDER = ("ok", "fail", "hold")


def _check_python() -> Dict[str, Any]:
    version = platform.python_version()
    major, minor = (int(p) for p in version.split(".")[:2])
    ok = (major, minor) >= (3, 12)
    return {"status": "ok" if ok else "fail", "python": version,
            "detail": "Python 3.12+ required" if ok else "Python 3.12+ required (found " + version + ")"}


def _check_state_dir(path: str) -> Dict[str, Any]:
    if not os.path.isdir(path):
        return {"status": "fail", "detail": "state directory does not exist"}
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        return {"status": "fail", "detail": "state directory must not be group or world writable"}
    if os.path.islink(path):
        return {"status": "fail", "detail": "state directory must not be a symlink"}
    return {"status": "ok", "detail": "mode {}".format(oct(mode))}


def _check_sqlite() -> Dict[str, Any]:
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE probe (x INTEGER)")
        connection.close()
    except sqlite3.Error:
        return {"status": "fail", "detail": "sqlite is unusable"}
    return {"status": "ok", "detail": "sqlite " + sqlite3.sqlite_version}


def _check_loopback() -> Dict[str, Any]:
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()
    except OSError:
        return {"status": "fail", "detail": "cannot bind loopback"}
    return {"status": "ok", "detail": "ephemeral loopback bind ok (e.g. port " + str(port) + ")"}


def _check_repo_tests() -> Dict[str, Any]:
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=root, capture_output=True, text=True, timeout=900)
    return {"status": "ok" if result.returncode == 0 else "fail",
            "detail": "unittest suite exit " + str(result.returncode)}


def _check_resources() -> Dict[str, Any]:
    """Report the resource profile and the host memory the profile can see."""
    from .resources import detect_memory, detect_swap, memory_pressure

    total, available = detect_memory()
    if total is None:
        return {"status": "hold", "detail": "host memory is not reported on this platform"}
    share = memory_pressure()
    swap_total, swap_free = detect_swap()
    detail = "{} MB RAM total, {} MB available".format(total, available)
    if swap_total is not None:
        detail += "; swap {} MB total, {} MB free".format(swap_total, swap_free)
    if share is not None and share < 0.1:
        detail += " (pressure: less than 10% RAM available)"
    return {"status": "ok", "detail": detail}


def run_checks(state_dir: str = "local-state", include_tests: bool = True) -> Dict[str, Any]:
    checks = {
        "python": _check_python(),
        "sqlite": _check_sqlite(),
        "loopback": _check_loopback(),
        "state_dir": _check_state_dir(state_dir),
        "resources": _check_resources(),
    }
    if include_tests:
        checks["repo_tests"] = _check_repo_tests()
    overall = "ok" if all(c["status"] == "ok" for c in checks.values()) else "fail"
    if any(c["status"] == "hold" for c in checks.values()):
        overall = "hold"
    return {"overall": overall, "checks": checks, "live_acceptance": "HOLD"}


def render(payload: Dict[str, Any]) -> str:
    lines = ["boru doctor"]
    for name, check in sorted(payload["checks"].items()):
        lines.append("- {}: {} ({})".format(name, check["status"], check.get("detail", "")))
    lines.append("overall: " + payload["overall"])
    lines.append("live_acceptance: " + payload["live_acceptance"])
    return "\n".join(lines)
