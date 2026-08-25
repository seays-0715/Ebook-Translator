"""Centralized language registry for translation UI and jobs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    name_en: str


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


def all_codes() -> list[str]:
    return [lang.code for lang in LANGUAGES]


def all_display_names() -> list[str]:
    return [lang.name_en for lang in LANGUAGES]


def normalize_code(code: str | None) -> str:
    """Validate a canonical supported language code. Raises ValueError otherwise."""
    if code is None:
        raise ValueError("Unsupported language code: None")
    c = code.strip()
    if not c:
        raise ValueError("Unsupported language code: ''")
    if c in _BY_CODE:
        return c
    lower = c.lower()
    for k, lang in _BY_CODE.items():
        if k.lower() == lower:
            return lang.code
    raise ValueError(f"Unsupported language code: {code!r}")


def code_to_name(code: str | None) -> str:
    """Human-readable English name for prompts and UI."""
    c = normalize_code(code)
    return _BY_CODE[c].name_en


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
