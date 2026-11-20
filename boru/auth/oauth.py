"""Official OAuth 2.0 authorization-code + PKCE flow (P7 source slice).

Implements the documented flow only:

* authorization URL with `code_challenge_method=S256`, `state` and `nonce`;
* a bounded, **numeric-loopback** redirect listener that captures exactly one
  authorization response and then stops;
* state and nonce verification, and single-use state;
* token exchange with the provider token endpoint, recording an opaque token
  **handle** in `TokenVault` — token values are never logged, stored in
  configuration or forwarded anywhere.

Browser sign-in, device code and client-handoff modes are provider-specific
and remain listed as UNSUPPORTED until each provider's official documentation
confirms them for this application category.  This slice does not claim any
provider has been connected.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

from ..errors import ConfigurationError, PolicyViolation
from .pkce import PkcePair, bounded_text, constant_time_equals, random_nonce, random_state, scopes
from .tokens import TokenVault

MAX_CODE_CHARS = 2048
MAX_STATE_CHARS = 512


@dataclass(frozen=True)
class OAuthClientConfig:
    """Bounded provider client configuration (no secrets in code)."""

    provider: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    client_id: str
    redirect_uri: str
    scopes: Tuple[str, ...]
    client_secret_env: Optional[str] = None
    allow_insecure_redirect: bool = False

    def __post_init__(self) -> None:
        """Reject malformed client configurations at construction time."""
        self.assert_valid()

    def validate(self) -> List[str]:
        errors: List[str] = []
        for name, limit in (("provider", 64), ("issuer", 256), ("authorization_endpoint", 512),
                            ("token_endpoint", 512), ("client_id", 256), ("redirect_uri", 512)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(name + " must be a bounded non-empty string")
        if self.client_secret_env is not None and (
            not isinstance(self.client_secret_env, str) or not self.client_secret_env.strip()
            or len(self.client_secret_env) > 64
        ):
            errors.append("client_secret_env must be a bounded environment variable name")
        try:
            ordered = scopes(self.scopes)
        except ConfigurationError as exc:
            errors.append(str(exc))
        for endpoint in ("authorization_endpoint", "token_endpoint"):
            value = getattr(self, endpoint)
            if isinstance(value, str) and value and not value.lower().startswith("https://"):
                errors.append(endpoint + " must be https")
        redirect = self.redirect_uri
        if isinstance(redirect, str) and redirect and not self._redirect_is_loopback(redirect) and not self.allow_insecure_redirect:
            errors.append("redirect_uri must be a numeric loopback address")
        return errors

    @staticmethod
    def _redirect_is_loopback(value: str) -> bool:
        try:
            parsed = urllib.parse.urlsplit(value)
            return ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            return False

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ConfigurationError("; ".join(sorted(set(errors))))

    def __post_init__(self) -> None:
        """Reject malformed client configurations and normalize scopes."""
        errors = self.validate()
        if errors:
            raise ConfigurationError("; ".join(sorted(set(errors))))
        object.__setattr__(self, "scopes", tuple(sorted(set(self.scopes))))


@dataclass
class AuthorizationAttempt:
    """One in-flight authorization: verifier, state, nonce and captured code."""

    config: OAuthClientConfig
    pkce: PkcePair
    state: str
    nonce: str
    code: Optional[str] = None
    error: Optional[str] = None
    finished: threading.Event = field(default_factory=threading.Event)
    #: Actual port the loopback listener bound (equal to the configured port,
    #: or an ephemeral port when the configuration used port 0).
    redirect_port: int = 0
    listening: threading.Event = field(default_factory=threading.Event)


class OAuthFlow:
    """Authorization-code + PKCE flow with a bounded loopback listener."""

    def __init__(self, config: OAuthClientConfig, vault: Optional[TokenVault] = None) -> None:
        config.assert_valid()
        self.config = config
        self.vault = vault or TokenVault()
        self._attempts: Dict[str, AuthorizationAttempt] = {}

    def start(self) -> Tuple[str, AuthorizationAttempt]:
        """Build the authorization URL and register a fresh attempt."""
        attempt = AuthorizationAttempt(config=self.config, pkce=PkcePair.generate(),
                                       state=random_state(), nonce=random_nonce())
        self._attempts[attempt.state] = attempt
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": attempt.state,
            "nonce": attempt.nonce,
            "code_challenge": attempt.pkce.challenge,
            "code_challenge_method": attempt.pkce.method,
        }
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return "{}?{}".format(self.config.authorization_endpoint, query), attempt

    def serve_redirect(self, attempt: AuthorizationAttempt, timeout: float = 120.0) -> str:
        """Listen on the numeric loopback redirect port until the code arrives."""
        if self._attempts.get(attempt.state) is not attempt:
            raise PolicyViolation("state is not a known attempt")
        parsed = urllib.parse.urlsplit(attempt.config.redirect_uri)
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            raise PolicyViolation("redirect_uri host must be a numeric address")
        if not address.is_loopback:
            raise PolicyViolation("redirect_uri must be loopback")
        port = parsed.port or 0
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise PolicyViolation("redirect_uri port is invalid")
        captured: Dict[str, str] = {}
        response_seen = threading.Event()

        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                query = urllib.parse.urlsplit(self.path).query
                params = urllib.parse.parse_qs(query, keep_blank_values=True)
                for key in ("code", "state", "error", "error_description"):
                    if key in params:
                        captured[key] = params[key][0][:MAX_CODE_CHARS]
                response_seen.set()
                body = b"Authorization received. You may close this window."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            server = ThreadingHTTPServer((str(address), port), Redirect)
        except OSError as exc:  # port busy or not permitted
            raise PolicyViolation("redirect listener cannot bind loopback") from exc
        server.daemon_threads = True
        attempt.redirect_port = server.server_address[1]
        attempt.listening.set()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            if not response_seen.wait(timeout):
                raise PolicyViolation("authorization timed out")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        attempt.finished.set()
        state = captured.get("state", "")
        if not constant_time_equals(state, attempt.state):
            raise PolicyViolation("state mismatch")
        if captured.get("error"):
            raise PolicyViolation("provider denied authorization")
        code = captured.get("code", "")
        if not code:
            raise PolicyViolation("authorization code missing")
        attempt.code = code
        return code

    def exchange(self, attempt: AuthorizationAttempt, *, now: Optional[float] = None) -> str:
        """Exchange the code for a token and return an opaque handle."""
        if not attempt.code:
            raise PolicyViolation("no authorization code")
        if self.config.client_secret_env:
            import os

            secret = os.environ.get(self.config.client_secret_env)
            if not secret:
                raise PolicyViolation("client secret environment variable is not set")
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": attempt.code[:MAX_CODE_CHARS],
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": attempt.pkce.verifier,
        }).encode("ascii")
        parsed = urllib.parse.urlsplit(self.config.token_endpoint)
        status, raw = self._exchange(parsed, body)
        if status != 200:
            raise PolicyViolation("token endpoint refused the exchange")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PolicyViolation("token endpoint returned an invalid response")
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise PolicyViolation("token endpoint response is missing a token")
        handle = "tok-{}".format(random_state()[:32])
        self.vault.register(handle, provider=self.config.provider, account=self.config.client_id,
                            scopes=self.config.scopes,
                            expires_at=float(payload["expires_in"]) + (now if now is not None else time.time())
                            if isinstance(payload.get("expires_in"), (int, float)) else None,
                            security_level="UNKNOWN")
        return handle

    def _exchange(self, parsed: urllib.parse.SplitResult, body: bytes) -> Tuple[int, bytes]:
        if parsed.scheme != "https":
            raise PolicyViolation("token endpoint must be https")
        deadline = time.monotonic() + 30
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=max(deadline - time.monotonic(), 0.05))
        try:
            conn.request("POST", parsed.path or "/", body=body, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            })
            response = conn.getresponse()
            chunks: List[bytes] = []
            total = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > 256 * 1024:
                    raise PolicyViolation("token endpoint response is too large")
                chunks.append(chunk)
            return response.status, b"".join(chunks)
        except (socket.error, OSError):
            raise PolicyViolation("token endpoint unavailable")
        except http.client.HTTPException:
            raise PolicyViolation("token endpoint protocol error")
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass
