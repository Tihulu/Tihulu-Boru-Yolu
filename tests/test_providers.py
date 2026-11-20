"""Provider tests: mock evidence and a bounded Jan text-only transport.

The Jan tests run against a test-owned loopback fixture server.  They are
MOCK/FIXTURE evidence for the transport contract, not a live Jan run.
"""
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boru.providers.base import ChatMessage, ChatReply, ProviderFailure
from boru.providers.jan import JanProvider
from boru.providers.mock import MockProvider


def messages():
    return [ChatMessage("user", "remember blue"), ChatMessage("assistant", "ack"), ChatMessage("user", "2 + 2 is")]


class MockProviderTests(unittest.TestCase):
    def test_replies_are_simulated_and_bounded(self):
        provider = MockProvider()
        self.assertEqual(("mock-text-v1",), provider.discover())
        reply = provider.chat("mock-text-v1", messages())
        self.assertEqual("simulated", reply.evidence_class)
        self.assertEqual("mock", reply.provider)
        self.assertTrue(reply.request_id.startswith("mock-"))
        self.assertIn("content", reply.to_dict())

    def test_unknown_model_refused(self):
        with self.assertRaises(ProviderFailure) as raised:
            MockProvider().chat("elsewhere", messages())
        self.assertEqual("model_missing", raised.exception.category)

    def test_no_conversation_refused(self):
        with self.assertRaises(ProviderFailure):
            MockProvider().chat("mock-text-v1", [ChatMessage("system", "hello")])

    def test_message_validation(self):
        for bad in ("", "   ", 5, "x" * 40000):
            with self.assertRaises(ValueError):
                ChatMessage("user", bad)
        with self.assertRaises(ValueError):
            ChatMessage("tool", "ok")  # tool output is not a chat role


class JanEndpointTests(unittest.TestCase):
    def test_remote_and_alias_endpoints_rejected(self):
        for bad in ("http://8.8.8.8:1337/v1", "http://localhost:1337/v1", "http://127.0.0.1:1337/../v1",
                    "https://example.com/v1", "http://user:pw@127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1?a=1",
                    "http://127.0.0.1:8080/v1#frag", "ftp://127.0.0.1:8080/v1", "http://[::1"):
            with self.assertRaises(ValueError):
                JanProvider(bad, local_model_ids=("m",), tool_execution_disabled=True)

    def test_tools_flag_must_be_explicitly_disabled(self):
        with self.assertRaises(ValueError):
            JanProvider("http://127.0.0.1:8080/v1", local_model_ids=("m",), tool_execution_disabled=False)

    def test_allowlist_required_and_validated(self):
        with self.assertRaises(ValueError):
            JanProvider("http://127.0.0.1:8080/v1", local_model_ids=(), tool_execution_disabled=True)
        for bad in (("",), ("m", "m"), ("x" * 200,)):
            with self.assertRaises(ValueError):
                JanProvider("http://127.0.0.1:8080/v1", local_model_ids=bad, tool_execution_disabled=True)

    def test_loopback_ipv6_accepted(self):
        provider = JanProvider("http://[::1]:8080/v1", local_model_ids=("m",), tool_execution_disabled=True)
        self.assertEqual(("m",), provider.discover())


class _Fixture(BaseHTTPRequestHandler):
    """Test-owned Jan-like fixture; only /v1/chat/completions is served."""

    def log_message(self, *args):  # keep test output quiet
        return

    def do_POST(self):
        self.server.paths.append(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8")) if body else {}
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": "not found"})
            return
        if payload.get("tool_choice") != "none" or payload.get("tools"):
            self._json(400, {"error": "tools are not permitted"})
            return
        response = self.server.script(payload)
        if isinstance(response, tuple):
            status, data = response
        else:
            status, data = 200, response
        self._json(status, data)

    def _json(self, status, data):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class JanTransportTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Fixture)
        self.server.paths = []
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:{}/v1".format(self.server.server_address[1])
        self.provider = JanProvider(self.base, local_model_ids=("local-model",), tool_execution_disabled=True)
        self.calls = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def script(self, payload):
        self.calls.append(payload)
        return {
            "id": "req-{}".format(len(self.calls)),
            "model": payload["model"],
            "choices": [{"message": {"role": "assistant", "content": "blue"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24},
        }

    def test_three_turn_conversation(self):
        self.server.script = self.script
        reply = self.provider.chat("local-model", messages(), max_tokens=64, timeout=5)
        self.assertEqual("direct", reply.evidence_class)
        self.assertEqual("blue", reply.content)
        self.assertEqual("req-1", reply.request_id)
        self.assertEqual({"input_tokens": 20, "output_tokens": 4, "total_tokens": 24}, dict(reply.usage))
        payload = self.calls[-1]
        self.assertEqual("/v1/chat/completions", self.server.paths[-1])
        self.assertEqual("local-model", payload["model"])
        self.assertEqual("none", payload["tool_choice"])
        self.assertNotIn("tools", payload)
        self.assertEqual(3, len(payload["messages"]))
        self.assertEqual(["user", "assistant", "user"], [m["role"] for m in payload["messages"]])

    def test_unknown_allowlist_model_refused_without_call(self):
        self.server.script = self.script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("remote-model", messages(), timeout=5)
        self.assertEqual("policy_denied", raised.exception.category)
        self.assertEqual([], self.calls)

    def test_bad_max_tokens_refused_without_call(self):
        self.server.script = self.script
        for bad in (0, True, 9999, "64"):
            with self.assertRaises(ProviderFailure):
                self.provider.chat("local-model", messages(), max_tokens=bad, timeout=5)
        self.assertEqual([], self.calls)

    def test_bad_timeout_refused(self):
        self.server.script = self.script
        with self.assertRaises(ProviderFailure):
            self.provider.chat("local-model", messages(), timeout=0.01)

    def test_tool_call_response_denied(self):
        def script(payload):
            self.calls.append(payload)
            return 200, {"id": "req-t", "model": "local-model",
                         "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "call"}]}}]}

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertEqual("policy_denied", raised.exception.category)

    def test_model_mismatch_denied(self):
        def script(payload):
            self.calls.append(payload)
            return 200, {"id": "req-x", "model": "other-model",
                         "choices": [{"message": {"role": "assistant", "content": "hi"}}]}

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertEqual("invalid_response", raised.exception.category)

    def test_missing_request_id_denied(self):
        def script(payload):
            self.calls.append(payload)
            return 200, {"model": "local-model", "choices": [{"message": {"role": "assistant", "content": "hi"}}]}

        self.server.script = script
        with self.assertRaises(ProviderFailure):
            self.provider.chat("local-model", messages(), timeout=5)

    def test_malformed_json_rejected(self):
        def script(payload):
            self.calls.append(payload)
            return 200, "not-json"

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertEqual("invalid_response", raised.exception.category)

    def test_duplicate_json_keys_rejected(self):
        def script(payload):
            self.calls.append(payload)
            return 200, '{"id":"a","id":"b","model":"local-model","choices":[{"message":{"role":"assistant","content":"hi"}}]}'

        self.server.script = script
        with self.assertRaises(ProviderFailure):
            self.provider.chat("local-model", messages(), timeout=5)

    def test_non_finite_json_rejected(self):
        def script(payload):
            self.calls.append(payload)
            return 200, '{"id":"a","model":"local-model","usage":{"prompt_tokens":NaN},"choices":[{"message":{"role":"assistant","content":"hi"}}]}'

        self.server.script = script
        with self.assertRaises(ProviderFailure):
            self.provider.chat("local-model", messages(), timeout=5)

    def test_http_status_categories(self):
        for status, category in ((401, "unauthorized"), (404, "model_missing"), (429, "rate_limited"),
                                 (500, "server_error"), (503, "server_error")):
            def script(payload, status=status):
                self.calls.append(payload)
                return status, {"error": "x"}

            self.server.script = script
            with self.assertRaises(ProviderFailure) as raised:
                self.provider.chat("local-model", messages(), timeout=5)
            self.assertEqual(category, raised.exception.category)

    def test_redirect_not_followed(self):
        def script(payload):
            self.calls.append(payload)
            return 302, {"location": "http://example.com/"}

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertEqual("policy_denied", raised.exception.category)

    def test_oversize_response_rejected(self):
        def script(payload):
            self.calls.append(payload)
            return 200, {"id": "req-big", "model": "local-model",
                         "choices": [{"message": {"role": "assistant", "content": "x" * 300000}}]}

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertEqual("request_too_large", raised.exception.category)

    def test_error_messages_never_carry_provider_text(self):
        def script(payload):
            self.calls.append(payload)
            return 200, "SECRET-PROVIDER-BODY"

        self.server.script = script
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("local-model", messages(), timeout=5)
        self.assertNotIn("SECRET-PROVIDER-BODY", str(raised.exception))

    def test_invalid_usage_shape_rejected(self):
        def script(payload):
            self.calls.append(payload)
            return 200, {"id": "req-u", "model": "local-model",
                         "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                         "usage": {"prompt_tokens": "many"}}

        self.server.script = script
        with self.assertRaises(ProviderFailure):
            self.provider.chat("local-model", messages(), timeout=5)


if __name__ == "__main__":
    unittest.main()


class JanDiscoveryTests(unittest.TestCase):
    """Opt-in, loopback model listing against a test-owned Jan-shaped server."""

    def setUp(self):
        self.models = {"data": [{"id": "local-a"}, {"id": "remote-b"}]}
        self.requests = []

        class Server(_Fixture):
            def do_GET(self):
                self.server.requests.append(self.path)
                raw = json.dumps(self.server.models).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
        self.server.daemon_threads = True
        self.server.requests = []
        self.server.models = self.models
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:{}/v1".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def provider(self, **kwargs):
        options = dict(local_model_ids=("local-a",), tool_execution_disabled=True)
        options.update(kwargs)
        return JanProvider(self.base, **options)

    def test_discovery_is_off_by_default(self):
        with self.assertRaises(ProviderFailure) as raised:
            self.provider().discover_models()
        self.assertEqual("policy_denied", raised.exception.category)
        self.assertEqual([], self.server.requests)

    def test_discovery_returns_only_allowlisted_ids(self):
        provider = self.provider(allow_discovery=True)
        self.assertEqual(("local-a",), provider.discover_models())
        self.assertEqual(["/v1/models"], self.server.requests)

    def test_missing_allowlisted_model_is_reported(self):
        provider = self.provider(local_model_ids=("absent",), allow_discovery=True)
        with self.assertRaises(ProviderFailure) as raised:
            provider.discover_models()
        self.assertEqual("model_missing", raised.exception.category)

    def test_health_reports_only_a_count(self):
        payload = self.provider(allow_discovery=True).health()
        self.assertEqual({"status": "ok", "models_listed": 2}, payload)
        self.assertNotIn("local-a", json.dumps(payload))

    def test_bad_timeouts_are_refused_without_a_request(self):
        for bad in (0, True, "5", 999):
            with self.assertRaises(ProviderFailure):
                self.provider(allow_discovery=True).health(timeout=bad)
        self.assertEqual([], self.server.requests)

    def test_bad_discovery_flag_is_refused(self):
        with self.assertRaises(ValueError):
            JanProvider(self.base, local_model_ids=("m",), tool_execution_disabled=True,
                        allow_discovery="yes")
