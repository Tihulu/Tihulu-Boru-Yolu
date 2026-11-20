"""OAuth PKCE flow tests (P7): loopback listener, state/nonce, token handles.

All provider interaction is against a test-owned loopback endpoint. No provider
is connected and no credential is used.
"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boru.auth import OAuthClientConfig, OAuthFlow, PkcePair, TokenVault, constant_time_equals


def config(**overrides):
    base = dict(provider="test-provider", issuer="https://accounts.example.test",
                authorization_endpoint="https://accounts.example.test/authorize",
                token_endpoint="https://accounts.example.test/token",
                client_id="test-client", redirect_uri="http://127.0.0.1:0/callback",
                scopes=("openid", "email"))
    base.update(overrides)
    return OAuthClientConfig(**base)


class _StubToken(BaseHTTPRequestHandler):
    """Test-owned token endpoint stub."""

    bodies: list = []
    status = 200
    payload = {"access_token": "stub-access-token", "expires_in": 3600, "scope": "openid email"}

    def log_message(self, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        type(self).bodies.append(self.rfile.read(length).decode("utf-8"))
        raw = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class ConfigValidationTests(unittest.TestCase):
    def test_https_only_endpoints(self):
        for bad in (dict(authorization_endpoint="http://insecure.test/authorize"),
                    dict(token_endpoint="http://insecure.test/token")):
            with self.assertRaises(Exception):
                config(**bad)

    def test_redirect_must_be_loopback(self):
        for bad in ("https://evil.example/callback", "http://8.8.8.8:9000/callback", "notaurl"):
            with self.assertRaises(Exception):
                config(redirect_uri=bad)

    def test_fields_are_bounded_and_unique(self):
        with self.assertRaises(Exception):
            config(scopes=("openid", "openid"))
        with self.assertRaises(Exception):
            config(client_id="")
        with self.assertRaises(Exception):
            config(client_secret_env="x" * 200)

    def test_bounded_scopes_are_sorted(self):
        self.assertEqual(("email", "openid"), tuple(sorted(config(scopes=("openid", "email")).scopes)))


class PkceTests(unittest.TestCase):
    def test_challenge_is_derived_from_verifier(self):
        pair = PkcePair.generate()
        self.assertEqual("S256", pair.method)
        self.assertTrue(43 <= len(pair.verifier) <= 128)
        self.assertEqual(pair.challenge, PkcePair.from_verifier(pair.verifier).challenge)

    def test_bad_verifier_rejected(self):
        for bad in ("short", "x" * 200, 5):
            with self.assertRaises(Exception):
                PkcePair.from_verifier(bad)

    def test_constant_time_compare(self):
        self.assertTrue(constant_time_equals("state", "state"))
        self.assertFalse(constant_time_equals("state", "other"))
        self.assertFalse(constant_time_equals("state", 5))


class AuthorizationUrlTests(unittest.TestCase):
    def test_url_is_pkce_and_state_bound(self):
        flow = OAuthFlow(config())
        url, attempt = flow.start()
        for expected in ("response_type=code", "client_id=test-client", "code_challenge=",
                         "code_challenge_method=S256", "state=", "nonce=", "redirect_uri=",
                         "scope=email%20openid"):
            self.assertIn(expected, url, expected)
        self.assertTrue(attempt.pkce.verifier)
        self.assertTrue(attempt.state)
        self.assertTrue(attempt.nonce)
        self.assertEqual("S256", attempt.pkce.method)

    def test_two_attempts_have_distinct_state(self):
        flow = OAuthFlow(config())
        _, first = flow.start()
        _, second = flow.start()
        self.assertNotEqual(first.state, second.state)
        self.assertNotEqual(first.nonce, second.nonce)

    def test_unknown_attempt_is_refused(self):
        from boru.errors import PolicyViolation

        flow = OAuthFlow(config())
        _, attempt = flow.start()
        other = OAuthFlow(config())
        _, other_attempt = other.start()
        with self.assertRaises(PolicyViolation):
            flow.serve_redirect(other_attempt, timeout=0.1)

    def test_loopback_listener_is_required(self):
        from boru.errors import PolicyViolation

        flow = OAuthFlow(config())
        _, attempt = flow.start()
        cfg = OAuthClientConfig(provider="p", issuer="https://i.test",
                                authorization_endpoint="https://i.test/authorize",
                                token_endpoint="https://i.test/token", client_id="c",
                                redirect_uri="http://0.0.0.0:9100/callback",
                                scopes=("openid",), allow_insecure_redirect=True)
        attempt.config = cfg
        with self.assertRaises(PolicyViolation):
            flow.serve_redirect(attempt, timeout=0.1)


class RedirectCaptureTests(unittest.TestCase):
    """Loopback redirect capture: exact state, single response, no public bind."""

    def build(self, redirect_host="127.0.0.1"):
        probe = ThreadingHTTPServer((redirect_host, 0), _StubToken)
        port = probe.server_address[1]
        probe.server_close()
        config_obj = OAuthClientConfig(provider="test-provider",
                                       issuer="https://accounts.example.test",
                                       authorization_endpoint="https://accounts.example.test/authorize",
                                       token_endpoint="https://accounts.example.test/token",
                                       client_id="test-client",
                                       redirect_uri="http://{}:{}/callback".format(redirect_host, port),
                                       scopes=("openid",))
        return OAuthFlow(config_obj), port

    @staticmethod
    def _deliver(port, code, state):
        request = urllib.request.Request(
            "http://127.0.0.1:{}/callback?code={}&state={}".format(port, code, state))
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read()
        except urllib.error.HTTPError:
            pass

    def test_redirect_captures_code_with_exact_state(self):
        flow, port = self.build()
        _, attempt = flow.start()
        threading.Thread(target=self._deliver, args=(port, "delivered-code", attempt.state)).start()
        self.assertEqual("delivered-code", flow.serve_redirect(attempt, timeout=25))
        self.assertTrue(attempt.finished.is_set())
        self.assertTrue(attempt.code.startswith("delivered-code"))

    def test_state_mismatch_is_denied(self):
        from boru.errors import PolicyViolation

        flow, port = self.build()
        _, attempt = flow.start()
        threading.Thread(target=self._deliver, args=(port, "delivered-code", "wrong-state")).start()
        with self.assertRaises(PolicyViolation):
            flow.serve_redirect(attempt, timeout=10)
        self.assertIsNone(attempt.code)

    def test_provider_error_is_denied(self):
        from boru.errors import PolicyViolation

        flow, port = self.build()
        _, attempt = flow.start()

        def deliver_error(port, state):
            request = urllib.request.Request(
                "http://127.0.0.1:{}/callback?error=access_denied&state={}".format(port, state))
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    response.read()
            except urllib.error.HTTPError:
                pass

        threading.Thread(target=deliver_error, args=(port, attempt.state)).start()
        with self.assertRaises(PolicyViolation):
            flow.serve_redirect(attempt, timeout=10)
        self.assertIsNone(attempt.code)

    def test_timeout_denies(self):
        from boru.errors import PolicyViolation

        flow, port = self.build()
        _, attempt = flow.start()
        with self.assertRaises(PolicyViolation):
            flow.serve_redirect(attempt, timeout=0.2)


class TokenVaultTests(unittest.TestCase):
    def test_handles_never_carry_token_values(self):
        vault = TokenVault()
        entry = vault.register("tok-1", provider="test", account="client", scopes=("openid",),
                               expires_at=None, security_level="UNKNOWN")
        payload = json.dumps(entry.to_dict())
        self.assertNotIn("stub-access-token", payload)
        self.assertEqual("UNKNOWN", entry.security_level)

    def test_revocation(self):
        vault = TokenVault()
        vault.register("tok-2", provider="test", account="client", scopes=("openid",), expires_at=None)
        self.assertEqual("REVOKED", vault.revoke("tok-2").security_level)
        with self.assertRaises(Exception):
            vault.revoke("missing")

    def test_vault_paths_are_owner_only(self):
        import os
        import tempfile

        root = tempfile.mkdtemp(prefix="boru-vault-")
        os.chmod(root, 0o700)
        try:
            path = os.path.join(root, "handles.json")
            vault = TokenVault(path)
            vault.register("tok-3", provider="test", account="client", scopes=("openid",), expires_at=None)
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertEqual("tok-3", stored[0]["handle"])
            from stat import S_IMODE

            self.assertEqual(0, S_IMODE(os.stat(path).st_mode) & 0o077)
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
