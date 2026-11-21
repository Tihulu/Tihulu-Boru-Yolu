"""Boru Core command line interface (offline-first).

Every command is local and read/writes only the dedicated Boru state
directory the owner names.  Nothing here touches Jan, OpenCode, TIHULU-AUTO,
system services or network endpoints, and no credential is accepted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from .audit import RejectionLedger
from .config import CoreConfig, ProviderConfig, default_config
from .core import BoruCore
from .errors import BoruError, ConfigurationError, PolicyViolation
from .store import TaskStore
from .types import TaskEnvelope
from .scheduler import AgentSpec, AgentScheduler, build_envelopes

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130


def _emit(payload: Dict[str, Any], show_text: bool = False) -> None:
    """Print a bounded, safe JSON summary."""
    if not show_text:
        payload.pop("text", None)
    payload = {key: value for key, value in payload.items() if value is not None}
    sys.stdout.write(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")


def _load_config(path: Optional[str]) -> CoreConfig:
    if path:
        return CoreConfig.from_file(path)
    return default_config()


def _open_core(config: CoreConfig, state_dir: Optional[str],
              audit_dir: Optional[str] = None) -> BoruCore:
    store = TaskStore(state_dir, max_records=config.max_records) if state_dir else TaskStore(max_records=config.max_records)
    ledger = RejectionLedger(audit_dir) if audit_dir else None
    return BoruCore(config, store=store, audit=ledger)


def _task_from_file(path: str) -> TaskEnvelope:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except json.JSONDecodeError:
        raise ConfigurationError("task file is not valid JSON")
    except OSError:
        raise ConfigurationError("task file cannot be read")
    if not isinstance(raw, dict):
        raise ConfigurationError("task file must contain an object")
    return TaskEnvelope.from_dict(raw)


def _add_common_shorthands(target: argparse.ArgumentParser) -> None:
    """Repeat the global options on a subparser without clobbering their values."""
    target.add_argument("--config", dest="config", default=argparse.SUPPRESS,
                        help="path to a Boru Core JSON configuration")
    target.add_argument("--state-dir", dest="state_dir", default=argparse.SUPPRESS,
                        help="dedicated local-state relative directory for durable task state")
    target.add_argument("--show-text", action="store_true", default=argparse.SUPPRESS,
                        help="include local reply text in output (local owner only)")
    target.add_argument("--audit-dir", dest="audit_dir", default=argparse.SUPPRESS,
                        help="existing owner-only directory for the local rejection ledger")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boru", description="TIHULU Boru Yolu — offline-first Boru Core CLI")
    parser.add_argument("--config", dest="config", default=None, help="path to a Boru Core JSON configuration")
    parser.add_argument("--state-dir", dest="state_dir", default=None,
                        help="dedicated local-state relative directory for durable task state")
    parser.add_argument("--show-text", action="store_true", help="include local reply text in output (local owner only)")
    parser.add_argument("--audit-dir", dest="audit_dir", default=None,
                        help="existing owner-only directory for the local rejection ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the fixed offline synthetic task (mock provider, no network)")
    _add_common_shorthands(demo)
    run = sub.add_parser("run", help="submit and dispatch one queued task from a JSON file")
    _add_common_shorthands(run)
    run.add_argument("--task", required=True, help="path to a task JSON file")
    status = sub.add_parser("status", help="show bounded task status")
    _add_common_shorthands(status)
    status.add_argument("--task-id", required=True)
    cancel = sub.add_parser("cancel", help="cancel a task")
    _add_common_shorthands(cancel)
    cancel.add_argument("--task-id", required=True)
    review = sub.add_parser("review", help="explicitly accept or reject a reviewed task")
    _add_common_shorthands(review)
    review.add_argument("--task-id", required=True)
    review.add_argument("--accept", action="store_true", help="accept; omit to reject")
    providers = sub.add_parser("providers", help="list configured providers and models (no discovery calls)")
    _add_common_shorthands(providers)
    audit = sub.add_parser("audit", help="show recent rejection rows from the local ledger")
    _add_common_shorthands(audit)
    audit.add_argument("--limit", default="32", help="number of rows (1..1024)")
    plan = sub.add_parser("plan",
                           help="submit a dependency-aware plan of logical agents and run what is ready")
    _add_common_shorthands(plan)
    plan.add_argument("--file", required=True, help="path to a plan JSON file")
    queue = sub.add_parser("queue", help="list tasks awaiting an explicit owner review")
    _add_common_shorthands(queue)
    return parser


def _run_demo(args) -> int:
    config = _load_config(args.config)
    envelope = TaskEnvelope(task_id="demo-1", goal="Synthetic offline acknowledgement for the P1 demo.")
    with _open_core(config, args.state_dir, args.audit_dir) as core:
        core.submit(envelope)
        summary = core.dispatch_next() or {"task_id": envelope.task_id, "state": "MISSING"}
        _emit(dict(summary, demo=True, text=core.result_text(envelope.task_id) if args.show_text else None),
              args.show_text)
        return EXIT_REJECTED if summary.get("state") in ("FAILED",) else EXIT_OK


def _run_task(args) -> int:
    config = _load_config(args.config)
    envelope = _task_from_file(args.task)
    with _open_core(config, args.state_dir, args.audit_dir) as core:
        core.submit(envelope)
        summary = core.dispatch_next() or {"task_id": envelope.task_id, "state": "MISSING"}
        _emit(dict(summary, text=core.result_text(envelope.task_id) if args.show_text else None), args.show_text)
        return EXIT_REJECTED if summary.get("state") in ("FAILED",) else EXIT_OK


def _status(args) -> int:
    with _open_core(_load_config(args.config), args.state_dir) as core:
        _emit(core.status(args.task_id), args.show_text)
        return EXIT_OK


def _cancel(args) -> int:
    with _open_core(_load_config(args.config), args.state_dir) as core:
        _emit({"task_id": args.task_id, "state": core.cancel(args.task_id)}, args.show_text)
        return EXIT_OK


def _review(args) -> int:
    with _open_core(_load_config(args.config), args.state_dir) as core:
        _emit({"task_id": args.task_id, "state": core.review(args.task_id, accept=args.accept)}, args.show_text)
        return EXIT_OK


def _audit(args) -> int:
    """Print bounded rejection rows from the local ledger (no payloads, no paths)."""
    from .audit import RejectionLedger

    if not args.audit_dir:
        _emit({"error": "configuration_error", "detail": "--audit-dir is required"}, args.show_text)
        return EXIT_ERROR
    if not os.path.isdir(args.audit_dir):
        _emit({"error": "configuration_error", "detail": "--audit-dir must be an existing directory"},
              args.show_text)
        return EXIT_ERROR
    limit = args.limit
    if isinstance(limit, str):
        try:
            limit = int(limit)
        except ValueError:
            _emit({"error": "configuration_error", "detail": "limit must be an integer"}, args.show_text)
            return EXIT_ERROR
    with RejectionLedger(args.audit_dir) as ledger:
        try:
            rows = ledger.recent(limit)
        except ConfigurationError as exc:
            _emit({"error": exc.kind, "detail": str(exc)}, args.show_text)
            return EXIT_ERROR
    _emit({"rejections": rows, "live_acceptance": "HOLD"}, args.show_text)
    return EXIT_OK


def _plan(args) -> int:
    """Submit a dependency-aware plan and dispatch every ready task.

    Nothing runs before its dependencies reach DONE, and each completed reply
    stays in REVIEW until you accept it explicitly.
    """
    config = _load_config(args.config)
    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except json.JSONDecodeError:
        _emit({"error": "configuration_error", "detail": "plan file is not valid JSON"}, args.show_text)
        return EXIT_ERROR
    except OSError:
        _emit({"error": "configuration_error", "detail": "plan file cannot be read"}, args.show_text)
        return EXIT_ERROR
    if not isinstance(raw, dict):
        _emit({"error": "configuration_error", "detail": "plan file must contain an object"}, args.show_text)
        return EXIT_ERROR
    goal = raw.get("goal")
    agents = raw.get("agents")
    if not isinstance(goal, str) or not goal.strip():
        _emit({"error": "configuration_error", "detail": "plan needs a bounded goal"}, args.show_text)
        return EXIT_ERROR
    if not isinstance(agents, list) or not agents:
        _emit({"error": "configuration_error", "detail": "plan needs a non-empty agents list"}, args.show_text)
        return EXIT_ERROR
    specs = []
    for entry in agents:
        if not isinstance(entry, dict):
            _emit({"error": "configuration_error", "detail": "agents entries must be objects"}, args.show_text)
            return EXIT_ERROR
        unknown = sorted(set(entry) - {"agent_id", "task_id", "capability_tags", "depends_on",
                                      "large_local_model"})
        if unknown:
            _emit({"error": "configuration_error", "detail": "unknown agent field"}, args.show_text)
            return EXIT_ERROR
        tags = entry.get("capability_tags", [])
        depends = entry.get("depends_on", [])
        if not isinstance(tags, list) or not isinstance(depends, list):
            _emit({"error": "configuration_error", "detail": "capability_tags and depends_on must be lists"},
                  args.show_text)
            return EXIT_ERROR
        specs.append(AgentSpec(agent_id=str(entry.get("agent_id", "")), task_id=str(entry.get("task_id", "")),
                               capability_tags=tuple(str(t) for t in tags),
                               depends_on=tuple(str(d) for d in depends),
                               large_local_model=bool(entry.get("large_local_model", False))))
    with _open_core(config, args.state_dir, args.audit_dir) as core:
        try:
            core.submit_plan(specs, goal)
        except PolicyViolation as exc:
            _emit({"error": exc.kind, "detail": str(exc)}, args.show_text)
            return EXIT_REJECTED
        dispatched = []
        while True:
            summary = core.dispatch_ready()
            if summary is None:
                break
            dispatched.append({"task_id": summary["task_id"], "state": summary["state"],
                               "reason": summary.get("reason")})

        _emit({"plan": dispatched, "live_acceptance": "HOLD"}, args.show_text)
        return EXIT_OK


def _queue(args) -> int:
    """List tasks awaiting the owner's explicit review."""
    config = _load_config(args.config)
    with _open_core(config, args.state_dir, args.audit_dir) as core:
        rows = core.store.by_state(("REVIEW",))
    _emit({"awaiting_review": rows, "live_acceptance": "HOLD"}, args.show_text)
    return EXIT_OK


def _providers(args) -> int:
    config = _load_config(args.config)
    core = _open_core(config, args.state_dir)
    try:
        entries = [
            {"kind": entry.kind, "models": [] if entry.kind == "mock" else list(entry.local_model_ids),
             "connection_state": core.provider_states().get(entry.api_key_env or "", "local")
            if entry.kind == "cloud" else "local"}
            for entry in config.providers
        ]
    finally:
        core.close()
    _emit({"providers": entries, "identity_is_not_inference": True, "live_acceptance": "HOLD"}, args.show_text)
    return EXIT_OK


_HANDLERS = {
    "demo": _run_demo,
    "run": _run_task,
    "status": _status,
    "cancel": _cancel,
    "review": _review,
    "providers": _providers,
    "audit": _audit,
    "plan": _plan,
    "queue": _queue,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _HANDLERS[args.command](args)
    except ConfigurationError as exc:
        _emit({"error": exc.kind, "detail": str(exc)}, args.show_text)
        return EXIT_ERROR
    except BoruError as exc:
        _emit({"error": exc.kind, "detail": str(exc)}, args.show_text)
        return EXIT_REJECTED
    except KeyboardInterrupt:
        _emit({"error": "interrupted"})
        return EXIT_INTERRUPTED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
