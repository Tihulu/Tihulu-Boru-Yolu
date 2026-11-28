"""Dashboard slice tests: loopback status, review action and isolation."""
import json
import tempfile
import os
import stat
import threading
import re
import unittest
import urllib.error
import urllib.request

from boru.config import CoreConfig, ProviderConfig
from boru.core import BoruCore
from boru.dashboard import MAX_CONNECTIONS, BoruDashboard
from boru.types import TaskEnvelope


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        self.engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        self.engine.dispatch_next()
        self.dashboard = BoruDashboard(self.engine)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.engine.close()

    def get_html(self, path):
        with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path), timeout=5) as response:
            return response.status, response.headers.get("Content-Type"), response.read().decode("utf-8")

    def get(self, path):
        try:
            with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path), timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request("http://127.0.0.1:{}{}".format(self.port, path), data=data,
                                         method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_root_page_is_bounded_html(self):
        status, content_type, body = self.get_html("/")
        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn("LOCAL_ONLY", body)
        self.assertIn("HOLD", body)

    def test_status_is_bounded_and_policy_shaped(self):
        status, payload = self.get("/status")
        self.assertEqual(200, status)
        self.assertIn("policy", payload)
        self.assertEqual("LOCAL_ONLY", payload["policy"]["inference_scope"])
        self.assertEqual("LOCAL_ISOLATED", payload["policy"]["execution_profile"])
        self.assertIn("live_acceptance", payload)
        self.assertEqual("HOLD", payload["live_acceptance"])
        self.assertIn("t1", [task["task_id"] for task in payload["tasks"]])
        task = [t for t in payload["tasks"] if t["task_id"] == "t1"][0]
        self.assertEqual("REVIEW", task["state"])
        self.assertEqual("simulated", task["evidence_class"])

    def test_task_endpoint(self):
        status, payload = self.get("/task/t1")
        self.assertEqual(200, status)
        self.assertEqual("REVIEW", payload["state"])

    def test_unknown_task_is_404(self):
        status, payload = self.get("/task/nope")
        self.assertEqual(404, status)

    def test_review_action_requires_an_explicit_flag(self):
        status, payload = self.post("/review", {"task_id": "t1", "accept": True})
        self.assertEqual(200, status)
        self.assertEqual("DONE", payload["state"])
        status, payload = self.post("/review", {"task_id": "t1", "accept": True})
        self.assertEqual(409, status)

    def test_review_without_accept_rejects(self):
        status, payload = self.post("/review", {"task_id": "t1"})
        self.assertEqual(409, status)
        self.assertEqual("explicit_accept_required", payload["error"])
        self.assertEqual(409, self.post("/review", {"task_id": "t1", "accept": "yes"})[0])
        _, payload_status = self.get("/task/t1")
        self.assertEqual("REVIEW", payload_status["state"])

    def test_malformed_review_request(self):
        self.assertEqual(400, self.post("/review", {"accept": True})[0])
        self.assertEqual(404, self.get("/nope")[0])

    def test_non_loopback_bind_refused(self):
        from boru.dashboard import MAX_CONNECTIONS, BoruDashboard as Dashboard

        with self.assertRaises(ValueError):
            Dashboard(self.engine, host="0.0.0.0")

    def test_dashboard_runs_no_inference(self):
        status, payload = self.get("/status")
        self.assertEqual(200, status)
        self.assertEqual([], [t for t in payload["tasks"] if t["task_id"] == "t1" and t["state"] == "RUNNING"])
        self.assertEqual("HOLD", payload["live_acceptance"])


class DashboardHardeningTests(unittest.TestCase):
    """A local owner surface is still a surface: bounds and typed failures."""

    def setUp(self):
        self.engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        self.engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        self.engine.dispatch_next()
        self.dashboard = BoruDashboard(self.engine)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.engine.close()

    def get(self, path):
        try:
            with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path), timeout=5) as response:
                return response.status, dict(response.headers), response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read().decode("utf-8")

    def test_responses_carry_restrictive_headers(self):
        status, headers, _ = self.get("/status")
        self.assertEqual(200, status)
        self.assertIn("default-src", headers.get("Content-Security-Policy", ""))
        self.assertEqual("nosniff", headers.get("X-Content-Type-Options"))

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        status, _, _ = self.get("/task/" + "x" * 200)
        self.assertEqual(400, status)

    def test_a_malformed_content_length_is_a_bad_request(self):
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.putrequest("POST", "/review")
            connection.putheader("Content-Length", "not-a-number")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(400, response.status)
        finally:
            connection.close()

    def test_a_connection_limit_refuses_beyond_the_bound(self):
        import http.client

        connections = []
        try:
            # idle connections hold their slot until they close: past the bound
            # a further request is refused, never queued unbounded
            for _ in range(MAX_CONNECTIONS):
                connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                connection.connect()
                connections.append(connection)
            status, _, body = self.get("/status")
            self.assertEqual(503, status)
            self.assertIn("dashboard_busy", body)
        finally:
            for connection in connections:
                try:
                    connection.close()
                except OSError:
                    pass
        # the bound is per in-flight connection: after they close, requests work
        status, _, _ = self.get("/status")
        self.assertEqual(200, status)


if __name__ == "__main__":
    unittest.main()


class DashboardAuditTests(DashboardTests):
    """The dashboard exposes only bounded, sanitized review/audit views."""

    def setUp(self):
        from boru.audit import RejectionLedger

        super().setUp()
        self.dashboard.stop()
        self.ledger = RejectionLedger()
        self.dashboard = BoruDashboard(self.engine, audit=self.ledger)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.ledger.close()
        self.engine.close()

    def get(self, path):
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path),
                                        timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_audit_view_is_bounded_and_sanitized(self):
        self.ledger.record("policy", "task-1", "task_axes_refused", "policy")
        status, payload = self.get("/audit")
        self.assertEqual(200, status)
        self.assertEqual([{"category": "policy", "reason": "task_axes_refused", "subject": "task-1",
                           "detail_kind": "policy", "at": payload["rejections"][0]["at"]}],
                         [dict(row) for row in payload["rejections"]])
        self.assertNotIn("ping", repr(payload))
        self.assertEqual("HOLD", payload["live_acceptance"])

    def test_audit_view_without_a_ledger(self):
        dashboard = BoruDashboard(self.engine)
        dashboard.start()
        try:
            status, payload = self.get("/audit")
            self.assertEqual(200, status)
            self.assertEqual([], payload["rejections"])
        finally:
            dashboard.stop()

    def test_review_queue_view(self):
        status, payload = self.get("/queue")
        self.assertEqual(200, status)
        self.assertEqual(["t1"], [row["task_id"] for row in payload["awaiting_review"]])

    def test_root_page_contains_an_audit_section(self):
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:{}/".format(self.port), timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertIn("Recent rejections", body)
        self.assertIn("no rejections recorded", body)

    def test_loopback_only(self):
        from boru.dashboard import MAX_CONNECTIONS, BoruDashboard as Dashboard

        with self.assertRaises(ValueError):
            Dashboard(self.engine, host="0.0.0.0", audit=self.ledger)


if __name__ == "__main__":
    unittest.main()


class DashboardAuditTests(DashboardTests):
    """The dashboard exposes only bounded, sanitized review/audit views."""

    def setUp(self):
        from boru.audit import RejectionLedger

        super().setUp()
        self.dashboard.stop()
        self.ledger = RejectionLedger()
        self.dashboard = BoruDashboard(self.engine, audit=self.ledger)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.ledger.close()
        self.engine.close()

    def get(self, path):
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path),
                                        timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_audit_view_is_bounded_and_sanitized(self):
        self.ledger.record("policy", "task-1", "task_axes_refused", "policy")
        status, payload = self.get("/audit")
        self.assertEqual(200, status)
        self.assertEqual([{"category": "policy", "reason": "task_axes_refused", "subject": "task-1",
                           "detail_kind": "policy", "at": payload["rejections"][0]["at"]}],
                         [dict(row) for row in payload["rejections"]])
        self.assertNotIn("ping", repr(payload))
        self.assertEqual("HOLD", payload["live_acceptance"])

    def test_audit_view_without_a_ledger(self):
        dashboard = BoruDashboard(self.engine)
        dashboard.start()
        try:
            status, payload = self.get("/audit")
            self.assertEqual(200, status)
            self.assertEqual([], payload["rejections"])
        finally:
            dashboard.stop()

    def test_review_queue_view(self):
        status, payload = self.get("/queue")
        self.assertEqual(200, status)
        self.assertEqual(["t1"], [row["task_id"] for row in payload["awaiting_review"]])

    def test_root_page_contains_an_audit_section(self):
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:{}/".format(self.port), timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertIn("Recent rejections", body)
        self.assertIn("no rejections recorded", body)

    def test_loopback_only(self):
        from boru.dashboard import MAX_CONNECTIONS, BoruDashboard as Dashboard

        with self.assertRaises(ValueError):
            Dashboard(self.engine, host="0.0.0.0", audit=self.ledger)


class DashboardAccessibilityTests(DashboardTests):
    """The dashboard page carries landmarks, labels and a heading order."""

    def setUp(self):
        from boru.audit import RejectionLedger

        super().setUp()
        self.ledger = RejectionLedger()
        self.dashboard = BoruDashboard(self.engine, audit=self.ledger)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.ledger.close()
        self.engine.close()

    def page(self, path="/"):
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path), timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_landmarks_labels_and_heading_order(self):
        status, body = self.page()
        self.assertEqual(200, status)
        self.assertRegex(body, r'^<!doctype html><html lang="(en|tr|de)">')
        self.assertIn('aria-labelledby="policy-heading"', body)
        self.assertIn('aria-labelledby="tasks-heading"', body)
        self.assertIn('aria-labelledby="audit-heading"', body)
        self.assertIn('aria-labelledby="review-heading"', body)
        self.assertIn("<caption>", body)
        self.assertIn('id="review-task"', body)
        self.assertIn('<button type="submit"', body)
        headings = re.findall(r"<h([1-6])[^>]*>", body)
        self.assertTrue(headings)
        self.assertEqual("1", headings[0])
        self.assertTrue(all(int(current) <= int(nxt) + 1 for current, nxt in zip(headings, headings[1:])))

    def test_localized_labels_are_used(self):
        status, body = self.page("/?lang=tr")
        self.assertEqual(200, status)
        self.assertIn('lang="tr"', body)
        self.assertIn("Politika eksenleri", body)
        self.assertIn("Kabul et", body)

    def test_no_script_is_required(self):
        status, body = self.page()
        self.assertEqual(200, status)
        self.assertNotIn("<script", body)


class PolicyPanelTests(DashboardTests):
    """The four policy axes are shown separately and labelled (P9)."""

    def setUp(self):
        super().setUp()
        self.dashboard = BoruDashboard(self.engine)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.engine.close()

    def page(self, path="/"):
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path),
                                    timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_four_axes_are_separate_and_labelled(self):
        status, body = self.page()
        self.assertEqual(200, status)
        self.assertIn('aria-labelledby="axes-heading"', body)
        for label in ("Optimization (routing)", "Inference scope", "Execution profile",
                      "Disclosure policy"):
            self.assertIn(label, body, label)
        for value in ("AUTO", "LOCAL_ONLY", "LOCAL_ISOLATED", "MINIMUM_NECESSARY"):
            self.assertIn(value, body, value)

    def test_axes_are_localized(self):
        status, body = self.page("/?lang=tr")
        self.assertEqual(200, status)
        self.assertIn("Optimizasyon (yönlendirme)", body)
        self.assertIn("Çıkarım kapsamı", body)
        self.assertIn("Yürütme profili", body)
        self.assertIn("Açıklama politikası", body)

    def test_axes_use_a_description_list(self):
        status, body = self.page()
        self.assertEqual(200, status)
        self.assertIn("<dl>", body)
        self.assertIn("<dt>", body)
        self.assertIn("<dd>", body)

    def test_unknown_policy_is_not_invented(self):
        status, payload = self.get("/status")
        self.assertEqual(200, status)
        self.assertEqual(
            {"optimization_mode": "AUTO", "inference_scope": "LOCAL_ONLY",
             "execution_profile": "LOCAL_ISOLATED", "disclosure_policy": "MINIMUM_NECESSARY"},
            payload["policy"])
