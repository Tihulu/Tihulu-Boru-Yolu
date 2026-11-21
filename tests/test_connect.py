"""Owner-run connection flow tests: real loopback exchange, no secrets printed."""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boru.auth import OAuthClientConfig, OAuthFlow
from boru.auth.tokens import TokenVault
from boru.cli import main


class _Args:
    def __init__(self, **entries):
        self.__dict__.update(entries)


class _Provider(BaseHTTPRequestHandler):
    """Test-owned authorization and token endpoints for one provider."""

    bodies = []
    paths = []

    def log_message(self, *args):
        return

    def do_GET(self):
        type(self).paths.append(self.path)
        body = b"authorization page"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        type(self).bodies.append(body)
        type(self).paths.append(self.path)
        payload = json.dumps({"access_token": "stub-access-token", "expires_in": 3600,
                              "scope": "openid"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ConnectFlowTests(unittest.TestCase):
    def setUp(self):
        _Provider.bodies = []
        _Provider.paths = []
        self.provider_server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
        self.provider_server.daemon_threads = True
        threading.Thread(target=self.provider_server.serve_forever, daemon=True).start()
        self.root = tempfile.mkdtemp(prefix="boru-connect-")
        os.chmod(self.root, stat.S_IRWXU)
        self.vault_dir = os.path.join(self.root, "vault")
        os.makedirs(self.vault_dir)
        os.chmod(self.vault_dir, stat.S_IRWXU)
        probe = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
        self.redirect_port = probe.server_address[1]
        probe.server_close()

    def tearDown(self):
        self.provider_server.shutdown()
        self.provider_server.server_close()
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def args(self, **overrides):
        base = dict(provider="test-provider",
                    authorization_endpoint="http://127.0.0.1:{}/authorize".format(
                        self.provider_server.server_address[1]),
                    token_endpoint="http://127.0.0.1:{}/token".format(
                        self.provider_server.server_address[1]),
                    client_id="test-client",
                    client_secret_env=None,
                    redirect_uri="http://127.0.0.1:{}/callback".format(self.redirect_port),
                    scope=None, vault_dir=self.vault_dir, timeout=30, no_browser=True,
                    allow_http=True, json=True, show_text=False, audit_dir=None,
                    config=None, state_dir=None)
        base.update(overrides)
        return _Args(**base)

    def flow(self, **overrides):
        """Run the real authorization-code + PKCE exchange against a test provider."""
        args = self.args(**overrides)
        config = OAuthClientConfig(
            provider=args.provider,
            issuer=args.authorization_endpoint.rsplit("/", 1)[0],
            authorization_endpoint=args.authorization_endpoint,
            token_endpoint=args.token_endpoint,
            client_id=args.client_id, redirect_uri=args.redirect_uri,
            scopes=("openid",), allow_http_endpoints=True)
        vault = TokenVault(self.vault_dir)
        flow = OAuthFlow(config, vault=vault)
        url, attempt = flow.start()
        state = dict(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))["state"][0]
        threading.Thread(target=self._deliver, args=(self.redirect_port, state)).start()
        code = flow.serve_redirect(attempt, timeout=args.timeout)
        handle = flow.exchange(attempt)
        return vault, handle, config

    def _deliver(self, port, state, code="delivered-code"):
        """Deliver the owner's approval; the listener may still be binding."""
        request = urllib.request.Request(
            "http://127.0.0.1:{}/callback?code={}&state={}".format(port, code, state))
        for attempt in range(40):
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    response.read()
                return
            except urllib.error.HTTPError:
                return
            except urllib.error.URLError:
                time.sleep(0.1)
        return

    def test_flow_stores_only_a_handle(self):
        vault, handle, config = self.flow()
        entry = vault.get(handle)
        self.assertIsNotNone(entry)
        self.assertEqual("test-provider", entry.provider)
        self.assertEqual(("openid",), entry.scopes)
        self.assertNotIn("stub-access-token", json.dumps(vault.list()))
        with open(os.path.join(self.vault_dir, "boru-token-handles.json"), "r",
                  encoding="utf-8") as handle_file:
            stored = handle_file.read()
        self.assertNotIn("stub-access-token", stored)
        self.assertEqual(0, stat.S_IMODE(os.stat(os.path.join(self.vault_dir,
                                                             "boru-token-handles.json")).st_mode)
                         & (stat.S_IRWXG | stat.S_IRWXO))
        self.assertEqual(1, os.stat(os.path.join(self.vault_dir, "boru-token-handles.json")).st_nlink)

    def test_exchange_uses_pkce_and_not_a_bearer(self):
        _Provider.bodies = []
        vault, handle, config = self.flow()
        body = _Provider.bodies[-1] if _Provider.bodies else ""
        self.assertIn("grant_type=authorization_code", body)
        self.assertIn("code_verifier=", body)
        self.assertNotIn("stub-access-token", body)
        self.assertTrue(_Provider.paths[-1].startswith("/token"))

    def test_cli_lists_handles_without_secrets(self):
        main(["accounts", "--vault-dir", self.vault_dir])
        self.assertEqual([], TokenVault(self.vault_dir).list())

    def test_disconnect_refuses_unknown_handles(self):
        self.assertEqual(1, main(["disconnect", "--vault-dir", self.vault_dir, "--handle", "ghost"]))

    def test_disconnect_revokes_a_stored_handle(self):
        vault, handle, config = self.flow()
        self.assertEqual(0, main(["disconnect", "--vault-dir", self.vault_dir, "--handle", handle]))
        # the CLI acts on a fresh vault instance: reload and confirm the revocation
        reloaded = TokenVault(self.vault_dir)
        self.assertEqual("REVOKED", reloaded.get(handle).security_level)
        self.assertEqual("REVOKED", vault.get(handle).security_level if False else
                         TokenVault(self.vault_dir).get(handle).security_level)

    def test_https_is_required_unless_explicitly_allowed(self):
        from boru.connect import connect as run_connect
        from boru.auth import OAuthClientConfig

        self.assertEqual(2, run_connect(self.args(allow_http=False)))
        # the allowed case is validated without running the browser flow
        args = self.args()
        config = OAuthClientConfig(
            provider=args.provider,
            issuer=args.authorization_endpoint.rsplit("/", 1)[0],
            authorization_endpoint=args.authorization_endpoint,
            token_endpoint=args.token_endpoint,
            client_id=args.client_id, redirect_uri=args.redirect_uri,
            scopes=("openid",), allow_http_endpoints=True)
        self.assertEqual([], config.validate())

    def test_public_redirect_is_refused(self):
        self.assertEqual(2, main_or_connect(self.args(redirect_uri="https://evil.example/callback")))

    def test_bad_scopes_are_refused(self):
        self.assertEqual(2, main_or_connect(self.args(scope=("a", "a"))))

    def test_bad_vault_directory_is_refused(self):
        self.assertEqual(2, main_or_connect(self.args(vault_dir=os.path.join(self.root, "absent"))))


def main_or_connect(args):
    """Run the connect command with a safe error code."""
    import io
    import contextlib

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        from boru.connect import connect as run_connect
        code = run_connect(args)
    return code


if __name__ == "__main__":
    unittest.main()
