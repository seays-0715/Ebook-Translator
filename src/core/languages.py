"""Centralized language registry for translation UI and jobs.

Source of truth: current Hy-MT2 supported-language table
(https://huggingface.co/unsloth/Hy-MT2-7B-GGUF — 38 entries including
Traditional Chinese and Cantonese).

UI displays human-readable names; jobs/API use stable codes.
There is no Auto Detect — the user always selects source and target.
Unknown or empty codes raise ValueError (no silent fallback).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    name_en: str


# Official codes from the current Hy-MT2 model card table (order preserved).
LANGUAGES: tuple[Language, ...] = (
    Language("zh", "Chinese"),
    Language("en", "English"),
    Language("fr", "French"),
    Language("pt", "Portuguese"),
    Language("es", "Spanish"),
    Language("ja", "Japanese"),
    Language("tr", "Turkish"),
    Language("ru", "Russian"),
    Language("ar", "Arabic"),
    Language("ko", "Korean"),
    Language("th", "Thai"),
    Language("it", "Italian"),
    Language("de", "German"),
    Language("vi", "Vietnamese"),
    Language("ms", "Malay"),
    Language("id", "Indonesian"),
    Language("tl", "Filipino"),
    Language("hi", "Hindi"),
    Language("zh-Hant", "Traditional Chinese"),
    Language("pl", "Polish"),
    Language("cs", "Czech"),
    Language("nl", "Dutch"),
    Language("km", "Khmer"),
    Language("my", "Burmese"),
    Language("fa", "Persian"),
    Language("gu", "Gujarati"),
    Language("ur", "Urdu"),
    Language("te", "Telugu"),
    Language("mr", "Marathi"),
    Language("he", "Hebrew"),
    Language("bn", "Bengali"),
    Language("ta", "Tamil"),
    Language("uk", "Ukrainian"),
    Language("bo", "Tibetan"),
    Language("kk", "Kazakh"),
    Language("mn", "Mongolian"),
    Language("ug", "Uyghur"),
    Language("yue", "Cantonese"),
)

_BY_CODE: dict[str, Language] = {lang.code: lang for lang in LANGUAGES}

# Alternate codes → registry codes (no "auto"; unknown codes raise).
_ALIASES: dict[str, str] = {
    "zh-TW": "zh-Hant",
    "zh-HK": "zh-Hant",
    "zh-CN": "zh",
    "zh-Hans": "zh",
}


def all_codes() -> list[str]:
    return [lang.code for lang in LANGUAGES]


def all_display_names() -> list[str]:
    return [lang.name_en for lang in LANGUAGES]


def normalize_code(code: str | None) -> str:
    """Resolve aliases and validate. Raises ValueError if unsupported."""
    if code is None:
        raise ValueError("Unsupported language code: None")
    c = code.strip()
    if not c:
        raise ValueError("Unsupported language code: ''")
    if c in _BY_CODE:
        return c
    if c in _ALIASES:
        return _ALIASES[c]
    lower = c.lower()
    for k, lang in _BY_CODE.items():
        if k.lower() == lower:
            return lang.code
    if lower in _ALIASES:
        return _ALIASES[lower]
    raise ValueError(f"Unsupported language code: {code!r}")


def code_to_name(code: str | None) -> str:
    """Human-readable English name for prompts and UI."""
    c = normalize_code(code)
    lang = _BY_CODE.get(c)
    return lang.name_en if lang else c


def name_to_code(name: str | None) -> str | None:
    """Map displayed English name back to code; None if unknown."""
    n = (name or "").strip()
    if not n:
        return None
    for lang in LANGUAGES:
        if lang.name_en == n or lang.code == n:
            return lang.code
    try:
        return normalize_code(n)
    except ValueError:
        return None


def display_pairs() -> list[tuple[str, str]]:
    """(display_name, code) pairs for UI OptionMenus."""
    return [(lang.name_en, lang.code) for lang in LANGUAGES]
