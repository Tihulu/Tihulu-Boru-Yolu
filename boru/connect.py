"""Owner-run provider connection flow (P7 slice): browser sign-in, honest state.

`boru connect` runs the official authorization-code + PKCE flow the owner
configures: it builds the authorization URL, opens the owner's system browser,
captures exactly one loopback redirect, exchanges the code and stores only an
opaque token handle. Sign-in state is reported as:

* `configured` — endpoint, models and scopes declared;
* `authenticated` — an identity exists (token present), which is **not**
  inference authorization;
* `model_test_passed` — only after a real authorized model call.

The command never prints a token, never writes one to a log and never claims an
entitlement. Registration with a provider is an owner action; this repository
connects nobody by itself.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import webbrowser
from typing import Any, Dict, Optional, Sequence

from .auth import OAuthClientConfig, OAuthFlow
from .auth.tokens import TokenVault
from .errors import ConfigurationError, PolicyViolation

CONNECTION_STATES = ("configured", "authenticated", "model_test_passed", "unavailable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boru-connect",
                                     description="Owner-run provider connection (OAuth/PKCE)")
    parser.add_argument("--provider", required=True, help="provider name, e.g. openai")
    parser.add_argument("--authorization-endpoint", required=True, help="https authorization endpoint")
    parser.add_argument("--token-endpoint", required=True, help="https token endpoint")
    parser.add_argument("--client-id", required=True, help="registered client id")
    parser.add_argument("--client-secret-env", default=None,
                        help="environment variable holding the client secret (private clients)")
    parser.add_argument("--redirect-uri", default="http://127.0.0.1:8731/callback",
                        help="numeric loopback redirect uri")
    parser.add_argument("--scope", action="append", default=None,
                        help="scope(s) to request, e.g. --scope openid --scope email")
    parser.add_argument("--vault-dir", required=True,
                        help="existing owner-only directory for the token vault")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="authorization wait, seconds (1..3600)")
    parser.add_argument("--no-browser", action="store_true",
                        help="print the authorization URL instead of opening a browser")
    parser.add_argument("--dry-run", action="store_true",
                         help="validate the registration values and the loopback port, then stop: "
                              "no browser, no authorization request")
    parser.add_argument("--allow-http", action="store_true",
                        help="owner opt-in for http endpoints (tests or a pinned local provider only)")

    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    return parser


#: An owner-run authorization waits a bounded time: a command that can hang for
#: days is not a bound, it is a trap.
MIN_AUTHORIZATION_TIMEOUT = 1.0
MAX_AUTHORIZATION_TIMEOUT = 3600.0


def connect(args: argparse.Namespace) -> int:
    timeout = getattr(args, "timeout", 180.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not MIN_AUTHORIZATION_TIMEOUT <= float(timeout) <= MAX_AUTHORIZATION_TIMEOUT:
        return _fail(args, "configuration_error",
                     "authorization timeout must be {}..{} seconds".format(
                         int(MIN_AUTHORIZATION_TIMEOUT), int(MAX_AUTHORIZATION_TIMEOUT)))
    scopes = tuple(sorted(set(args.scope or ["openid"])))
    try:
        config = OAuthClientConfig(
            provider=args.provider,
            issuer=args.authorization_endpoint.rsplit("/", 1)[0],
            authorization_endpoint=args.authorization_endpoint,
            token_endpoint=args.token_endpoint,
            client_id=args.client_id,
            redirect_uri=args.redirect_uri,
            scopes=scopes,
            client_secret_env=args.client_secret_env,
            allow_http_endpoints=getattr(args, "allow_http", False),
        )
        config.assert_valid()
    except (PolicyViolation, ConfigurationError, ValueError) as exc:
        return _fail(args, "configuration_error", str(exc))
    try:
        readiness = _readiness(config, args.vault_dir)
    except PolicyViolation as exc:
        return _fail(args, "not_ready", str(exc))
    vault = TokenVault(args.vault_dir)
    flow = OAuthFlow(config, vault=vault)
    url, attempt = flow.start()
    if args.dry_run:
        # Validate everything the owner supplied, then stop before the browser:
        # a registration that cannot work is refused before it is attempted.
        _out(args, dict(readiness, authorization_url=url, state_length=len(attempt.state),
                        dry_run=True, live_acceptance="HOLD"))
        return 0
    if args.no_browser:
        _out(args, {"authorization_url": url, "state_hint": "open this URL in your browser"})
    else:
        opened = webbrowser.open(url)
        if not opened:
            _out(args, {"authorization_url": url, "note": "browser did not open; open the URL manually"})
    try:
        code = flow.serve_redirect(attempt, timeout=float(timeout))
    except PolicyViolation as exc:
        return _fail(args, "authorization_failed", str(exc))
    try:
        handle = flow.exchange(attempt)
    except PolicyViolation as exc:
        return _fail(args, "token_exchange_failed", str(exc))
    entry = vault.get(handle)
    _out(args, {
        "provider": config.provider,
        "connection_state": vault_connection_state(vault, handle),
        "handle": entry.handle if entry else handle,
        "scopes": list(entry.scopes) if entry else list(scopes),
        "expires_at": entry.expires_at if entry else None,
        "model_test_passed": False,
        "identity_is_not_inference": True,
        "live_acceptance": "HOLD",
    })
    return 0


def _readiness(config: OAuthClientConfig, vault_dir: str) -> Dict[str, Any]:
    """Report whether the supplied values can complete a connection at all.

    Checked without contacting the provider: the endpoints are https, the
    redirect is numeric loopback, the scopes are bounded, the vault directory is
    usable and the redirect port is bindable on this host right now.
    """
    import socket

    from urllib.parse import urlsplit

    for name in ("authorization_endpoint", "token_endpoint"):
        parsed = urlsplit(getattr(config, name))
        if parsed.scheme != "https":
            raise PolicyViolation(name + " must be https")
    redirect = urlsplit(config.redirect_uri)
    port = redirect.port
    if port is None or not 1 <= port <= 65535:
        raise PolicyViolation("redirect uri must name a port")
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise PolicyViolation("redirect port {} is not bindable: {}".format(port, exc.strerror))
    finally:
        probe.close()
    if not os.path.isdir(vault_dir):
        raise PolicyViolation("vault directory must already exist")
    mode = stat.S_IMODE(os.stat(vault_dir).st_mode)
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PolicyViolation("vault directory must not be group or world writable")
    return {
        "endpoints_https": True,
        "redirect_loopback_port": port,
        "redirect_port_bindable": True,
        "scopes": list(config.scopes),
        "vault_directory": "owner-only" if not mode & (stat.S_IRWXG | stat.S_IRWXO) else "accessible-to-others",
        "provider": config.provider,
        "client_id_length": len(config.client_id),
    }


def vault_connection_state(vault: TokenVault, handle: str) -> str:
    entry = vault.get(handle)
    if entry is None or entry.security_level == "REVOKED":
        return "unavailable"
    return "authenticated"


def _out(args, payload: Dict[str, Any]) -> None:
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")
    else:
        for key, value in payload.items():
            sys.stdout.write("{}: {}\n".format(key, value))


def _fail(args, code: str, detail: str) -> int:
    _out(args, {"error": code, "detail": detail, "live_acceptance": "HOLD"})
    return 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    return connect(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
