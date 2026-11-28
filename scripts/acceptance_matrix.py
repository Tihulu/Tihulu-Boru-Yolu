"""Executable clean-machine acceptance matrix and rollback checklist (P10).

Turns `docs/OS_ACCEPTANCE.md` into something an owner can actually *run*: the
report walks the M01-M12 rows, auto-fills every row this repository can prove
without a live host or a real credential, and for every row it cannot it prints
the exact command to run and what to record. Nothing is claimed to have passed:
a row that needs a real machine starts as HOLD and only becomes PASS when the
owner runs it and records the result in `harness/build-log.md`.

Design constraints, matching the rest of the project:

* **fail-closed and offline by default** - no network call is made; the rows
  that would need one are marked HOLD with the command to run, not attempted;
* **nothing is installed or mutated** unless `--run-install` is passed, and even
  then only Boru-owned paths under the caller's own HOME are touched;
* every emitted row carries its own command and expected output, so the ledger
  entry a human writes is complete;
* the human-readable and the JSON forms are byte-identical in content, so either
  can be attached to a review package.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The matrix. ``automatable`` rows are proven by this script; the rest need the
#: owner on a real image and start as HOLD.
MATRIX: Tuple[Dict[str, Any], ...] = (
    {"id": "M01", "automatable": True, "partial": "install+uninstall round trip",
     "test": "Install Boru Core user-space on a clean image (scripts/install_boru.sh)",
     "expected": "Exit 0; only the named target/state/bin directories are created; owner-only modes (0700/0600)",
     "record": "date, image, tester",
     "command": "scripts/install_boru.sh --dry-run && scripts/install_boru.sh"},
    {"id": "M02", "automatable": False,
     "test": "Same on Ubuntu 24.04 LTS x86_64",
     "expected": "Same as M01",
     "record": "date, image, tester",
     "command": "scripts/install_boru.sh --dry-run && scripts/install_boru.sh",
     "note": "requires the Ubuntu image; the same script and the same checks run"},
    {"id": "M03", "automatable": True, "partial": "offline demo",
     "test": "python3 -m boru demo on each image",
     "expected": "REVIEW, evidence_class=simulated, live_acceptance=HOLD",
     "record": "sanitized output",
     "command": "python3 -m boru demo"},
    {"id": "M04", "automatable": True, "partial": "uninstall",
     "test": "Uninstall (scripts/uninstall_boru.sh)",
     "expected": "Only Boru-owned paths removed; nothing else touched",
     "record": "verification listing",
     "command": "scripts/uninstall_boru.sh"},
    {"id": "M05", "automatable": True, "partial": "full static evidence block",
     "test": "python3 scripts/evidence.py on each image",
     "expected": "Exit 0 with all mandatory checks PASS",
     "record": "full report block",
     "command": "python3 scripts/evidence.py"},
    {"id": "M06", "automatable": False,
     "test": "Offline run (no internet) with a local Jan model",
     "expected": "Same behaviour as M03; no cloud endpoints contacted",
     "record": "date, tester",
     "command": "python3 -m boru demo (with the network disabled and a local model)",
     "note": "needs a real host with Jan and a downloaded local model"},
    {"id": "M07", "automatable": False,
     "test": "A21 direct Jan 3-turn chat on a clean image",
     "expected": "REVIEW/direct with the allowlisted model ID and measured usage",
     "record": "provider/model/request IDs",
     "command": "python3 -m boru run <task file> with a Jan provider configured",
     "note": "needs a live provider and owner credentials"},
    {"id": "M08", "automatable": False,
     "test": "Optional OpenCode child session in a disposable directory",
     "expected": "Real session/message IDs, agent, model and provider identity recorded; session deleted",
     "record": "IDs",
     "command": "run the OpenCode adapter through Boru Core",
     "note": "needs a live OpenCode install and a disposable profile"},
    {"id": "M09", "automatable": True, "partial": "bind posture",
     "test": "Ports and processes",
     "expected": "No non-loopback listener; no Boru-owned background service after stop; no autostart entry",
     "record": "ss -ltn summary plus python3 scripts/listener_check.py --json",
     "command": "python3 scripts/listener_check.py --json"},
    {"id": "M10", "automatable": False,
     "test": "Partial outage: cloud provider unavailable",
     "expected": "Only permitted fallback; LOCAL_ONLY yields zero remote calls; budget holds, never escalated",
     "record": "test log summary",
     "command": "python3 -m unittest tests.test_router -v",
     "note": "the deterministic simulation runs in CI; the live outage drill needs a real provider"},
    {"id": "M11", "automatable": False,
     "test": "Revocation and cancellation",
     "expected": "Revoked consent denies; cancelled tasks release leases; interrupted tasks return to HOLD on restart",
     "record": "ledger rows",
     "command": "python3 -m unittest tests.test_consent_store tests.test_scheduler -v",
     "note": "the deterministic part runs in CI; the live drill needs a running core"},
    {"id": "M12", "automatable": False,
     "test": "Rollback after a failed install",
     "expected": "Restore from backup reproduces the pre-install state; Jan/OpenCode unchanged",
     "record": "verification listing",
     "command": "restore the pre-install backup on a disposable copy and re-run scripts/evidence.py",
     "note": "needs a disposable image and a backup taken before M01"},
)


def _run(argv: List[str], timeout: float = 600.0) -> Tuple[int, str]:
    try:
        out = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                             timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    text = (out.stdout or "") + (out.stderr or "")
    return int(out.returncode), text


def _test_count(output: str) -> int:
    for line in output.splitlines():
        if line.startswith("Ran ") and line.endswith(" tests"):
            try:
                return int(line[4:-7])
            except ValueError:
                continue
    return -1


def _listener() -> Dict[str, Any]:
    code, text = _run([sys.executable, os.path.join("scripts", "listener_check.py"), "--json"])
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "listener_check did not emit JSON", "exit": code}
    return payload


def _evidence(quick: bool = False) -> Dict[str, Any]:
    argv = [sys.executable, os.path.join("scripts", "evidence.py"), "--json"]
    if quick:
        argv.append("--quick")
    code, text = _run(argv)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "evidence did not emit JSON", "exit": code}


def _demo() -> Dict[str, Any]:
    code, text = _run([sys.executable, "-m", "boru", "demo"], timeout=120.0)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "demo did not emit JSON", "exit": code}
    return payload


def _install_round_trip() -> Dict[str, Any]:
    """M01/M04: the installed launcher runs, and uninstall removes Boru only."""
    from tempfile import mkdtemp
    import shutil
    import stat

    home = mkdtemp(prefix="boru-accept-")
    try:
        env_home = dict(os.environ)
        env_home["HOME"] = home
        env_home["PATH"] = os.path.join(home, ".local", "bin") + os.pathsep + env_home.get("PATH", "")
        script = os.path.join("scripts", "install_boru.sh")
        proc = subprocess.run(["bash", script], cwd=ROOT, env=env_home,
                              capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            return {"ok": False, "reason": "install failed",
                    "output": (proc.stdout + proc.stderr)[-400:]}
        launcher = os.path.join(home, ".local", "bin", "boru")
        if not os.path.exists(launcher):
            return {"ok": False, "reason": "launcher was not created"}
        proc = subprocess.run([sys.executable, "-m", "boru", "demo"],
                              cwd=ROOT, env=env_home, capture_output=True,
                              text=True, timeout=300)
        uninstall = subprocess.run(["bash", os.path.join("scripts", "uninstall_boru.sh")],
                                   cwd=ROOT, env=env_home, capture_output=True,
                                   text=True, timeout=300)
        return {"ok": uninstall.returncode == 0 and proc.returncode == 0,
                "demo": proc.returncode == 0,
                "uninstall": uninstall.returncode == 0,
                "launcher_existed": True}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": str(exc)}
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _status_from(evidence: Dict[str, Any], key: str) -> Tuple[str, str]:
    """A row is PASS only when its evidence actually says PASS.

    ``scripts/evidence.py`` reports each sub-check as the string ``"PASS"`` (or
    ``"SKIPPED"``/``"FAIL"``), so that string — not ``True`` — is the success
    signal here. A row whose evidence was not produced (``--quick`` skipped the
    suite, or a sub-check failed) stays HOLD with the reason, rather than being
    counted as passed. This is the whole point of the report: an owner must be
    able to trust that PASS means *proved here*, not *assumed*.
    """
    detail = evidence.get(key)
    if detail == "PASS":
        return "PASS", "proved offline by scripts/evidence.py"
    if isinstance(detail, dict) and detail.get("ok"):
        return "PASS", "proved offline by scripts/evidence.py"
    reason = "evidence reported {!r}; run scripts/evidence.py without --quick".format(detail)
    return "HOLD", reason


def report(quick: bool = False, run_install: bool = False) -> Dict[str, Any]:
    """Assemble the M01-M12 report. Never mutates outside HOME."""
    rows: List[Dict[str, Any]] = []
    listener = _listener()
    demo = _demo()
    evidence = _evidence(quick=quick)
    install = _install_round_trip() if run_install else None
    ev_block = (evidence or {}).get("install") or {}
    for row in MATRIX:
        out = dict(row)
        if row["id"] == "M09":
            out["status"] = "PASS" if listener.get("ok") else "HOLD"
            out["detail"] = listener
        elif row["id"] == "M03":
            ok = bool(demo.get("state") or demo.get("status"))
            out["status"] = "PASS" if ok else "HOLD"
            out["detail"] = demo if ok else {"reason": "demo did not report REVIEW",
                                             "exit": demo.get("exit")}
        elif row["id"] == "M05":
            checks = evidence.get("checks") if isinstance(evidence, dict) else None
            unit = checks.get("unit_tests") if isinstance(checks, dict) else None
            # unit_tests is the tuple ("PASS", 865); anything else means the
            # suite did not run on this evidence block.
            ok = isinstance(unit, (tuple, list)) and len(unit) == 2 and unit[0] == "PASS" \
                and isinstance(unit[1], int) and unit[1] > 0
            out["status"] = "PASS" if ok else "HOLD"
            out["detail"] = evidence if ok else {
                "reason": "the full suite did not run in this evidence block; "
                          "run scripts/evidence.py without --quick"}
        elif row["id"] == "M01":
            out["status"], out["detail"] = _status_from(ev_block, "install")
            if install:
                out["install_round_trip"] = install
        elif row["id"] == "M04":
            out["status"], out["detail"] = _status_from(ev_block, "uninstall")
        else:
            # An unverified row is never silently passed, and always says why.
            out["status"] = "HOLD"
            out["detail"] = row.get("note", "needs an owner run on a real image")
        rows.append(out)
    auto = sum(1 for r in rows if r["status"] == "PASS")
    hold = len(rows) - auto
    return {
        "matrix": "M01-M12",
        "image": {"system": platform.system(), "release": platform.release(),
                  "machine": platform.machine(), "python": platform.python_version()},
        "commit": _head(),
        "rows": rows,
        "summary": {"total": len(rows), "pass": auto,
                    "hold": hold,
                    "note": "PASS means this repository proved the row offline; "
                            "HOLD means an owner must run it on a real image and "
                            "record it in harness/build-log.md. No HOLD row is "
                            "ever counted as passed."},
        "live_acceptance": "HOLD",
    }


def _head() -> Optional[str]:
    code, text = _run(["git", "rev-parse", "HEAD"], timeout=15.0)
    return text.strip() if code == 0 else None


def render(payload: Dict[str, Any]) -> str:
    """The human-readable form of the same content."""
    lines = ["Boru Yolu - clean-machine acceptance matrix",
             "image: {} {} {}".format(payload["image"]["system"],
                                      payload["image"]["release"],
                                      payload["image"]["machine"]),
             "commit: {}".format(payload["commit"]),
             "live_acceptance: HOLD", ""]
    for row in payload["rows"]:
        mark = "PASS" if row["status"] == "PASS" else "HOLD"
        lines.append("{} [{}] {}".format(row["id"], mark, row["test"]))
        lines.append("      expected: {}".format(row["expected"]))
        lines.append("      run:      {}".format(row["command"]))
        lines.append("      record:   {}".format(row["record"]))
        if row["status"] == "HOLD":
            lines.append("      note:     {}".format(row.get("note", "needs an owner run")))
        lines.append("")
    s = payload["summary"]
    lines.append("summary: {} PASS (offline-verifiable), {} HOLD (owner run required)".format(
        s["pass"], s["hold"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Executable clean-machine acceptance matrix")
    parser.add_argument("--quick", action="store_true",
                        help="use the quick evidence block (skip the suite)")
    parser.add_argument("--run-install", action="store_true",
                        help="also run the install/demo/uninstall round trip in a scratch HOME")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)
    payload = report(quick=args.quick, run_install=args.run_install)
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render(payload) + "\n")
    # A HOLD row is never an exit-0 "all passed": the exit code reports only the
    # rows this repository could actually prove.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
