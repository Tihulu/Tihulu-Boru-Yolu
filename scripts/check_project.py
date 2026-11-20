#!/usr/bin/env python3
"""Static sample-contract checks only. NEVER authorizes or executes Shell."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID_OPT = {"AUTO", "ECONOMY", "BALANCED", "PERFORMANCE", "MANUAL"}
VALID_SCOPE = {"LOCAL_ONLY", "CLOUD_ALLOWED"}
VALID_PRIVACY = {"MINIMUM_NECESSARY", "SCOPED_APPROVED"}
VALID_EXEC = {"LOCAL_ISOLATED", "HYBRID_PRIVATE", "CLOUD_SHELL_APPROVAL", "CLOUD_SHELL_TRUSTED"}
CLOUD_SHELL = {"CLOUD_SHELL_APPROVAL", "CLOUD_SHELL_TRUSTED"}
REQUIRED_DOCS = [
    "AGENTS.md", "docs/CODEX_EXECUTION_PLAYBOOK.md",
    "docs/CODEX_START_PROMPT.md", "harness/build-log.md",
    "README.md", "docs/ARCHITECTURE.md", "docs/SECURITY_MODES.md",
    "docs/PRIVACY_BRIDGE.md", "docs/ROUTING_AND_RESOURCES.md",
    "docs/INTEGRATIONS.md", "docs/INSTALL_UBUNTU_POPOS.md",
    "docs/ROADMAP.md", "docs/ACCEPTANCE.md", "docs/THREAT_MODEL.md",
    "docs/OPERATIONS.md", "docs/ADRS/0001-control-plane-and-trust.md",
    "docs/ADRS/0002-shell-execution-profiles.md",
    "docs/ADRS/0003-boru-core-independence.md",
    "docs/ADRS/0004-preserve-modes-and-privacy.md", "examples/visual-flow.mmd",
]


def validate_example(c: dict) -> list[str]:
    """Validate documentation examples, NOT a production authorization engine."""
    errors = []
    try:
        orch = c["orchestrator"]
        if orch["engine"] != "boru_core":
            errors.append("Boru Core must own orchestration")
        if orch["tihulu_auto_required"] is not False:
            errors.append("TIHULU-AUTO must never be required")
        if orch["standalone_opencode"] is not True or orch["standalone_jan"] is not True:
            errors.append("OpenCode and Jan must remain standalone")
        if c["services"].get("tihulu_auto", {}).get("required", False):
            errors.append("legacy adapter must not be required")
        routing = c["routing"]
        exe = c["execution"]
        cs = exe["cloud_shell"]
        privacy = c["privacy"]
        deploy = c["deployment"]
        if c["schema_version"] != 1:
            errors.append("unsupported schema_version")
        if routing["optimization_mode"] not in VALID_OPT:
            errors.append("unknown optimization_mode")
        if routing["inference_scope"] not in VALID_SCOPE:
            errors.append("unknown inference_scope")
        if exe["profile"] not in VALID_EXEC:
            errors.append("unknown execution profile")
        if not isinstance(routing["max_agents"], int) or isinstance(routing["max_agents"], bool) or not 1 <= routing["max_agents"] <= 6:
            errors.append("max_agents must be 1..6")
        if routing["inference_scope"] == "LOCAL_ONLY" and routing["cloud_fallback_enabled"]:
            errors.append("LOCAL_ONLY forbids cloud fallback")
        if exe["profile"] in CLOUD_SHELL:
            if routing["inference_scope"] != "CLOUD_ALLOWED":
                errors.append("cloud Shell profile requires CLOUD_ALLOWED")
            if not cs["enabled"]:
                errors.append("cloud Shell profile requires cloud_shell enabled")
            if not cs["sandbox_required"] or not cs["live_owner_consent_required"]:
                errors.append("cloud Shell requires sandbox and independent owner consent")
        elif cs["enabled"]:
            errors.append("cloud_shell cannot be enabled in local-only Shell profile")
        if privacy["policy"] not in VALID_PRIVACY:
            errors.append("unknown privacy policy")
        if privacy["raw_tool_output_to_cloud"]:
            errors.append("raw_tool_output_to_cloud cannot be globally enabled")
        if not isinstance(privacy["max_result_fields"], int) or isinstance(privacy["max_result_fields"], bool) or privacy["max_result_fields"] < 1:
            errors.append("max_result_fields must be a positive integer")
        if not privacy["recipient_bound_disclosure_consent"]:
            errors.append("recipient-bound consent required")
        if deploy["auto_start"]:
            errors.append("pilot must not auto-start")
        if deploy["bind_host"] not in ("127.0.0.1", "::1", "localhost"):
            errors.append("pilot must be loopback only")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append("missing or malformed field: " + type(exc).__name__)
    return errors


def main() -> int:
    problems = []
    for name in REQUIRED_DOCS:
        if not (ROOT / name).is_file():
            problems.append("missing: " + name)
    config_path = ROOT / "examples/boru-yolu.example.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        problems.extend(validate_example(config))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append("sample config invalid: " + type(exc).__name__)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        return 1
    print("PASS: documentation manifest and sample policy invariants (static only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
