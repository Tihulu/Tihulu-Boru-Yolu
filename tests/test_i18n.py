"""Localization tests for the dashboard label set (P9)."""
import unittest

from boru.dashboard import BoruDashboard
from boru.i18n import LANGUAGES, summary_labels, translate


class I18nTests(unittest.TestCase):
    def test_supported_languages(self):
        self.assertEqual(("en", "tr", "de"), LANGUAGES)

    def test_labels_are_localized(self):
        self.assertEqual("Boru Core status", translate("title", "en"))
        self.assertEqual("Boru Core durumu", translate("title", "tr"))
        self.assertEqual("Boru Core-Status", translate("title", "de"))

    def test_unknown_language_falls_back(self):
        self.assertEqual("Boru Core status", translate("title", "fr"))
        self.assertEqual("status", translate("status"))  # english label

    def test_unknown_key_is_not_invented(self):
        self.assertEqual("definitely_missing", translate("definitely_missing", "tr"))

    def test_label_set_is_bounded_and_safe(self):
        labels = summary_labels("tr")
        self.assertTrue(labels)
        for key, value in labels.items():
            self.assertLessEqual(len(value), 64, key)
            self.assertNotIn("<", value)

    def test_no_task_or_secret_text_in_labels(self):
        for language in LANGUAGES:
            for value in summary_labels(language).values():
                self.assertNotIn("token", value.lower())
                self.assertNotIn("/home/", value)


class DashboardLanguageTests(unittest.TestCase):
    def setUp(self):
        from boru.config import CoreConfig, ProviderConfig
        from boru.core import BoruCore
        from boru.types import TaskEnvelope

        self.engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        self.engine.submit(TaskEnvelope(task_id="t1", goal="ping"))
        self.engine.dispatch_next()
        self.dashboard = BoruDashboard(self.engine)
        self.host, self.port = self.dashboard.start()

    def tearDown(self):
        self.dashboard.stop()
        self.engine.close()

    def get(self, path):
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, path), timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_root_page_is_localized_by_query(self):
        status, body = self.get("/?lang=tr")
        self.assertEqual(200, status)
        self.assertIn('lang="tr"', body)
        self.assertIn("Politika eksenleri", body)
        status, body = self.get("/?lang=de")
        self.assertIn("Boru Core-Status", body)
        status, body = self.get("/")
        self.assertIn('lang="en"', body)

    def test_unknown_language_query_falls_back_to_english(self):
        status, body = self.get("/?lang=fr")
        self.assertEqual(200, status)
        self.assertIn('lang="en"', body)

    def test_page_never_contains_the_task_goal(self):
        status, body = self.get("/")
        self.assertNotIn("ping", body)


if __name__ == "__main__":
    unittest.main()
