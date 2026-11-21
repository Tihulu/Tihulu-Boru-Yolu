"""Cloud provider (P7 source slice): validation, honest state, no live calls."""
import json
import os
import unittest

from boru.providers.base import ChatMessage, ChatReply, ProviderFailure
from boru.providers.cloud import CONNECTION_STATES, CloudProvider


def reply(model_id="m1", request_id="req-1", usage=None):
    payload = {"id": request_id, "model": model_id,
               "choices": [{"message": {"role": "assistant", "content": "ack"}}]}
    if usage:
        payload["usage"] = usage
    return json.dumps(payload).encode("utf-8")


def transport_factory(status=200, body=None, record=None):
    def transport(method, path, payload, timeout, api_key):
        if record is not None:
            record.append({"method": method, "path": path, "author": bool(api_key)})
        return status, body if body is not None else reply()

    return transport


class CloudValidationTests(unittest.TestCase):
    def test_https_required_unless_explicitly_allowed(self):
        with self.assertRaises(ValueError):
            CloudProvider("test", "http://api.example.test/v1", model_ids=("m",))
        provider = CloudProvider("test", "http://api.example.test/v1", model_ids=("m",), allow_http=True)
        self.assertFalse(provider._tls_flag)
        https = CloudProvider("test", "https://api.example.test/v1", model_ids=("m",))
        self.assertTrue(https._tls_flag)

    def test_bad_endpoints_rejected(self):
        for bad in ("https://user:pw@api.example.test/v1", "https://api.example.test/v1?a=1",
                    "https://api.example.test/v1#f", "ftp://api.example.test/v1", "", "https:///v1",
                    "https://api example.test/v1"):
            with self.assertRaises(ValueError):
                CloudProvider("test", bad, model_ids=("m",))

    def test_allowlist_required_and_validated(self):
        with self.assertRaises(ValueError):
            CloudProvider("test", "https://api.example.test/v1", model_ids=())
        for bad in (("",), ("m", "m"), ("x" * 200,)):
            with self.assertRaises(ValueError):
                CloudProvider("test", "https://api.example.test/v1", model_ids=bad)

    def test_bad_provider_name_rejected(self):
        for bad in ("", "x" * 100, 5):
            with self.assertRaises(ValueError):
                CloudProvider(bad, "https://api.example.test/v1", model_ids=("m",))

    def test_declared_local_flag_is_false(self):
        provider = CloudProvider("test", "https://api.example.test/v1", model_ids=("m",))
        self.assertFalse(provider.local)


class CloudStateTests(unittest.TestCase):
    def setUp(self):
        self.provider = CloudProvider("test", "https://api.example.test/v1", model_ids=("m1",),
                                      api_key_env="BORU_TEST_KEY")

    def tearDown(self):
        os.environ.pop("BORU_TEST_KEY", None)

    def test_configured_without_credential_is_not_authenticated(self):
        self.assertEqual("configured", self.provider.connection_state())
        self.assertIn("configured", CONNECTION_STATES)

    def test_authenticated_with_credential(self):
        os.environ["BORU_TEST_KEY"] = "value-not-logged"
        self.assertEqual("authenticated", self.provider.connection_state())

    def test_allowlist_blocks_other_models(self):
        os.environ["BORU_TEST_KEY"] = "v"
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("elsewhere", [ChatMessage("user", "hi")])
        self.assertEqual("policy_denied", raised.exception.category)

    def test_missing_credential_fails_closed(self):
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("m1", [ChatMessage("user", "hi")])
        self.assertEqual("unauthorized", raised.exception.category)

    def test_successful_call_is_direct_evidence_for_that_model(self):
        os.environ["BORU_TEST_KEY"] = "v"
        original = self.provider._exchange

        def exchange(method, path, payload, timeout, api_key):
            return 200, reply(model_id="m1", request_id="req-cloud",
                              usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4})

        self.provider._exchange = exchange
        result = self.provider.chat("m1", [ChatMessage("user", "hi")], max_tokens=16, timeout=10)
        self.assertEqual("direct", result.evidence_class)
        self.assertEqual("req-cloud", result.request_id)
        self.assertEqual("m1", result.model_id)
        self.assertEqual({"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}, dict(result.usage))
        self.provider._exchange = original

    def test_authorization_header_only_when_credential_exists(self):
        seen = []
        os.environ["BORU_TEST_KEY"] = "v"
        original = self.provider._exchange

        def exchange(method, path, payload, timeout, api_key):
            seen.append(api_key)
            return 200, reply()

        self.provider._exchange = exchange
        self.provider.chat("m1", [ChatMessage("user", "hi")])
        self.assertTrue(seen[0])
        os.environ.pop("BORU_TEST_KEY")
        try:
            self.provider.chat("m1", [ChatMessage("user", "hi")])
        except ProviderFailure:
            pass
        self.provider._exchange = original

    def test_error_status_mapping(self):
        os.environ["BORU_TEST_KEY"] = "v"
        for status, category in ((401, "unauthorized"), (404, "model_missing"), (429, "rate_limited"),
                                 (500, "server_error")):
            self.provider._exchange = transport_factory(status=status, body=b'{"error":"x"}')
            with self.assertRaises(ProviderFailure) as raised:
                self.provider.chat("m1", [ChatMessage("user", "hi")])
            self.assertEqual(category, raised.exception.category, status)

    def test_error_text_never_carries_provider_body(self):
        os.environ["BORU_TEST_KEY"] = "v"
        self.provider._exchange = transport_factory(status=200, body=b"SECRET-BODY")
        with self.assertRaises(ProviderFailure) as raised:
            self.provider.chat("m1", [ChatMessage("user", "hi")])
        self.assertNotIn("SECRET-BODY", str(raised.exception))

    def test_injected_transport_is_test_only(self):
        record = []
        self.provider._exchange = transport_factory(record=record)
        with self.assertRaises(ProviderFailure):
            self.provider.chat("m1", [ChatMessage("user", "hi")])  # no credential -> denied before send
        self.assertEqual([], record)


if __name__ == "__main__":
    unittest.main()
