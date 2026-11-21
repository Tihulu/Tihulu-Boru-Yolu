"""Dashboard localization (P9 slice): English, Turkish and German.

Only fixed, owner-visible labels are localized. No task content, provider
output, path or credential ever passes through this module.
"""
from __future__ import annotations

from typing import Dict, Tuple

DEFAULT_LANGUAGE = "en"
LANGUAGES: Tuple[str, ...] = ("en", "tr", "de")

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
