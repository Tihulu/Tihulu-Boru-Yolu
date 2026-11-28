"""Dashboard localization (P9 slice): English, Turkish and German.

Only fixed, owner-visible labels are localized. No task content, provider
output, path or credential ever passes through this module.
"""
from __future__ import annotations

from typing import Dict, Tuple

DEFAULT_LANGUAGE = "en"
LANGUAGES: Tuple[str, ...] = ("en", "tr", "de")

#: Repository text (source, docs, tests, commit messages, issues, PRs) is
#: English.  The user-facing dashboard localization is in product scope and is
#: the only permitted non-English text, together with the test that asserts it.
REPOSITORY_TEXT_EXEMPT = ("boru/i18n.py", "tests/test_dashboard.py")

#: Directories never scanned (version control metadata, caches, artifacts).
_SKIPPED_DIRECTORIES = frozenset({".git", "__pycache__", ".pytest_cache", "build", "dist"})

#: Turkish-specific code points, expressed as code points so that this file
#: stays English while still detecting every Turkish letter.
_NON_ENGLISH_CODEPOINTS: Tuple[int, ...] = (
    0x00C7, 0x00DC, 0x00D6,          # C, U, O with diaeresis/cedilla (upper)
    0x00E7, 0x00FC, 0x00F6,          # c, u, o with diaeresis/cedilla (lower)
    0x011E, 0x011F,                  # G with breve
    0x0130, 0x0131,                  # dotted and dotless I
    0x015E, 0x015F,                  # S with cedilla
    0x00DF,                          # sharp s (German, never repository text)
)
NON_ENGLISH_CHARS = frozenset(chr(code) for code in _NON_ENGLISH_CODEPOINTS)


def repository_files(root):
    """Every repository text file, tracked first and by walk outside a checkout.

    The English-text rule must hold in an unpacked source tree as well as in a
    git clone, so a missing ``git`` is a fallback, not an exemption.
    """
    import os
    import subprocess

    try:
        listed = subprocess.check_output(["git", "ls-files"], cwd=str(root), text=True).splitlines()
    except (OSError, subprocess.CalledProcessError):
        listed = []
    if listed:
        for name in listed:
            if name.strip():
                yield name
        return
    for current, directories, files in os.walk(str(root)):
        directories[:] = sorted(d for d in directories if d not in _SKIPPED_DIRECTORIES)
        for name in sorted(files):
            path = os.path.join(current, name)
            yield os.path.relpath(path, str(root)).replace(os.sep, "/")


def is_repository_english(text: str) -> bool:
    """True when a text carries no non-English letter.

    The predicate is deliberately letter-based: it marks text that cannot be
    English repository communication without judging prose that happens to
    quote another language.
    """
    if not isinstance(text, str):
        return True
    return not any(character in NON_ENGLISH_CHARS for character in text)

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "title": {"en": "Boru Core status", "tr": "Boru Core durumu", "de": "Boru Core-Status"},
    "policy": {"en": "Policy axes", "tr": "Politika eksenleri", "de": "Richtlinien-Achsen"},
    "optimization": {"en": "Optimization", "tr": "Optimizasyon", "de": "Optimierung"},
    "inference": {"en": "Inference scope", "tr": "Çıkarım kapsamı", "de": "Inferenz-Umfang"},
    "execution": {"en": "Execution profile", "tr": "Yürütme profili", "de": "Ausführungsprofil"},
    "disclosure": {"en": "Disclosure policy", "tr": "Açıklama politikası", "de": "Offenlegungsrichtlinie"},
    "tasks": {"en": "Tasks", "tr": "Görevler", "de": "Aufgaben"},
    "agents": {"en": "Agents", "tr": "Ajanlar", "de": "Agenten"},
    "providers": {"en": "Providers", "tr": "Sağlayıcılar", "de": "Anbieter"},
    "state": {"en": "State", "tr": "Durum", "de": "Zustand"},
    "evidence": {"en": "Evidence class", "tr": "Kanıt sınıfı", "de": "Belegklasse"},
    "live_acceptance": {"en": "Live acceptance", "tr": "Canlı kabul", "de": "Live-Abnahme"},
    "audit": {"en": "Recent rejections", "tr": "Son reddiyeler", "de": "Letzte Ablehnungen"},
    "hold": {"en": "HOLD", "tr": "BEKLEMEDE", "de": "ANGEHALTEN"},
    "review": {"en": "Review", "tr": "İnceleme", "de": "Überprüfung"},
    "axis_routing": {"en": "Optimization (routing)", "tr": "Optimizasyon (yönlendirme)",
                     "de": "Optimierung (Routing)"},
    "axis_inference": {"en": "Inference scope", "tr": "Çıkarım kapsamı", "de": "Inferenz-Umfang"},
    "axis_execution": {"en": "Execution profile", "tr": "Yürütme profili", "de": "Ausführungsprofil"},
    "axis_disclosure": {"en": "Disclosure policy", "tr": "Açıklama politikası",
                        "de": "Offenlegungsrichtlinie"},
    "accept": {"en": "Accept", "tr": "Kabul et", "de": "Annehmen"},
}


def translate(key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Return a localized fixed label.

    An unsupported language falls back to English; an unknown key falls back to
    the key itself so a typo is visible rather than silently mistranslated.
    """
    if language not in LANGUAGES:
        language = DEFAULT_LANGUAGE
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(language, entry[DEFAULT_LANGUAGE])


def summary_labels(language: str = DEFAULT_LANGUAGE) -> Dict[str, str]:
    """Return the bounded label set used by the dashboard template."""
    return {key: translate(key, language) for key in TRANSLATIONS}
