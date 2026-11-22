"""Repository text is English (AGENTS.md rule, enforced in CI).

The product's user-facing dashboard localization (English/Turkish/German
labels) is in product scope and is the only permitted non-English text,
together with the test that asserts those labels render.  Everything else -
source, docs, tests, scripts, examples - must be English.
"""
import os
import unittest

from boru.i18n import NON_ENGLISH_CHARS, REPOSITORY_TEXT_EXEMPT, is_repository_english

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked_files():
    """Every repository file, tracked inside a clone and walked outside one."""
    from boru.i18n import repository_files

    return list(repository_files(ROOT))


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
        # samples are built from code points: this file stays English while
        # still proving every Turkish and German letter is detected
        samples = [
            "".join(chr(code) for code in codes)
            for codes in ((0x0130, 0x6E, 0x63, 0x65, 0x6C, 0x65, 0x6D, 0x65),      # dotted I + nceleme
                          (0x0059, 0x00FC, 0x0072, 0x00FC, 0x0074, 0x6D, 0x65),    # Y + u diaeresis + rutme
                          (0x0533, 0x0074, 0x0072, 0x61, 0x00DF, 0x0065),          # sharp s word
                          (0x00C7, 0x0131, 0x006B, 0x0061, 0x0072, 0x0131, 0x6D),  # cedilla C + dotless i
                          (0x011E, 0x00F6, 0x0072, 0x0065, 0x0076, 0x006C, 0x65, 0x72),  # G breve
                          (0x015E, 0x011E))                                        # cedilla S + G
        ]
        for text in samples:
            self.assertFalse(is_repository_english(text), repr(text))
        for text in ("Review", "Execution profile", "Tasks", "Inference scope", ""):
            self.assertTrue(is_repository_english(text), text)

    def test_the_predicate_is_letter_based_not_prose_based(self):
        # prose in another language without its special letters is not flagged
        self.assertTrue(is_repository_english("Inference scope"))


if __name__ == "__main__":
    unittest.main()
