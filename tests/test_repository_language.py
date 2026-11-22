"""Repository text is English (AGENTS.md rule, enforced in CI).

The product's user-facing dashboard localization (English/Turkish/German
labels) is in product scope and is the only permitted non-English text,
together with the test that asserts those labels render.  Everything else -
source, docs, tests, scripts, examples - must be English.
"""
import os
import subprocess
import unittest

from boru.i18n import NON_ENGLISH_CHARS, REPOSITORY_TEXT_EXEMPT, is_repository_english

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked_files():
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [name for name in output.splitlines() if name.strip()]


class RepositoryLanguageTests(unittest.TestCase):
    def test_only_the_localization_set_is_not_english(self):
        offenders = []
        for name in tracked_files():
            if name in REPOSITORY_TEXT_EXEMPT:
                continue
            path = os.path.join(ROOT, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except (UnicodeDecodeError, OSError):
                continue
            if not is_repository_english(text):
                offenders.append(name)
        self.assertEqual([], offenders, "non-English repository text: " + ", ".join(offenders))

    def test_the_localization_set_is_exactly_the_dashboard_labels(self):
        self.assertEqual(("boru/i18n.py", "tests/test_dashboard.py"), REPOSITORY_TEXT_EXEMPT)

    def test_the_predicate_detects_turkish_and_german_letters(self):
        for text in ("İnceleme", "Yürütme", "Straße", "Çıkarım", "Görevler", "ŞĞ"):
            self.assertFalse(is_repository_english(text), text)
        for text in ("Review", "Execution profile", "Tasks", "Inference scope", ""):
            self.assertTrue(is_repository_english(text), text)

    def test_the_predicate_is_letter_based_not_prose_based(self):
        # prose in another language without its special letters is not flagged
        self.assertTrue(is_repository_english("Inference scope"))


if __name__ == "__main__":
    unittest.main()
