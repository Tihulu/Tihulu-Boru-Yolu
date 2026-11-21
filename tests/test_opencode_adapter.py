"""OpenCode adapter tests (P2): loopback-only, real session identity required."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boru.adapters.opencode import OpenCodeAdapter
from boru.errors import ConnectorDenied


class _Stub(BaseHTTPRequestHandler):
    """Test-owned OpenCode-shaped server: no subagent, no tools, no Shell."""

    calls: list = []
    session_id = "ses_test_0001"
    prompt_status = 200

    def log_message(self, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        self.calls.append(("POST", self.path, json.loads(body.decode("utf-8") or "{}")))
        if self.path == "/api/session":
            payload = json.dumps({"id": self.session_id, "title": "stub session"}).encode()
        elif self.path.startswith("/api/session/") and self.path.endswith("/prompt"):
            if type(self).prompt_status == 200:
                payload = json.dumps({"sessionID": type(self).session_id,
                                      "message": {"role": "assistant", "content": "ack"}}).encode()
            else:
                payload = b'{"error":"stub failure"}'
        elif self.path.endswith("/interrupt"):
            payload = b'{"ok":true}'
        else:
            self.send_error(404)
            return
        self.send_response(type(self).prompt_status if "/prompt" in self.path else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        _Stub.calls = []
        _Stub.prompt_status = 200
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.adapter = OpenCodeAdapter("http://127.0.0.1:{}/".format(self.server.server_address[1]))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_session_id_is_real(self):
        session = self.adapter.create_session()
        self.assertEqual("ses_test_0001", session)
        self.assertEqual(session, self.adapter.last_session_id)
        self.assertEqual(("POST", "/api/session", {}), _Stub.calls[0])

    def test_prompt_and_interact(self):
        session = self.adapter.create_session()
        reply = self.adapter.prompt(session, "synthetic request")
        self.assertEqual("ses_test_0001", reply["sessionID"])
        self.assertEqual("ack", reply["message"]["content"])
        self.assertEqual("POST", _Stub.calls[1][0])
        self.assertEqual({"text": "synthetic request"}, _Stub.calls[1][2])
        self.assertTrue(self.adapter.interrupt(session)["ok"])

    def test_error_mapping(self):
        session = self.adapter.create_session()
        for status, category in ((401, "unauthorized"), (404, "not_found"), (500, "server_error")):
            _Stub.prompt_status = status
            with self.assertRaises(ConnectorDenied) as raised:
                self.adapter.prompt(session, "x")
            self.assertEqual(category, str(raised.exception), status)
        _Stub.prompt_status = 200

    def test_loopback_hardening(self):
        for bad in ("http://8.8.8.8:4096/", "http://localhost:4096", "http://user:pw@127.0.0.1:4096",
                    "https://example.test", "http://127.0.0.1:4096/v1?x=1"):
            with self.assertRaises(ValueError):
                OpenCodeAdapter(bad)

    def test_bounded_prompt_text(self):
        session = self.adapter.create_session()
        self.adapter.prompt(session, "x" * 40000)
        # the request body is truncated to the bounded limit before sending
        sent = _Stub.calls[-1][2]["text"]
        self.assertEqual(32 * 1024, len(sent))

    def test_token_only_from_environment_name(self):
        import os

        os.environ["BORU_TEST_OC_TOKEN"] = "not-a-real-token"
        adapter = OpenCodeAdapter("http://127.0.0.1:{}/".format(self.server.server_address[1]),
                                  token_env="BORU_TEST_OC_TOKEN")
        adapter.create_session()
        del os.environ["BORU_TEST_OC_TOKEN"]
        self.assertTrue(_Stub.calls)


if __name__ == "__main__":
    unittest.main()
