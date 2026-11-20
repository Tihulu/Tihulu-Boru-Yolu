"""Dashboard slice tests: loopback status, review action and isolation."""
import json
import tempfile
import os
import stat
import threading
import unittest
import urllib.error
import urllib.request

from boru.config import CoreConfig, ProviderConfig
from boru.core import BoruCore
from boru.dashboard import BoruDashboard
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
        from boru.dashboard import BoruDashboard as Dashboard

        with self.assertRaises(ValueError):
            Dashboard(self.engine, host="0.0.0.0")

    def test_dashboard_runs_no_inference(self):
        status, payload = self.get("/status")
        self.assertEqual(200, status)
        self.assertEqual([], [t for t in payload["tasks"] if t["task_id"] == "t1" and t["state"] == "RUNNING"])
        self.assertEqual("HOLD", payload["live_acceptance"])


if __name__ == "__main__":
    unittest.main()
