"""Key-based i18n. V1: zh-HK / zh-TW + en. Fallback: en.

Spec §42.5: detect system UI language; fallback to English if unsupported.
Manual override via Settings.interface_language.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path

_DIR = Path(__file__).parent
_CACHE: dict[str, dict[str, str]] = {}
_CURRENT = "en"

# Supported UI language tables (filename stem under this package)
_SUPPORTED = ("en", "zh-HK")


def _load(lang: str) -> dict[str, str]:
    if lang in _CACHE:
        return _CACHE[lang]
    path = _DIR / f"{lang}.json"
    if not path.exists():
        base = lang.split("-")[0]
        path = _DIR / f"{base}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    _CACHE[lang] = data
    return data


def _normalize_to_ui_lang(raw: str | None) -> str | None:
    """Map system locale tags to a V1 UI table key (en | zh-HK)."""
    if not raw:
        return None
    s = raw.strip().replace("_", "-")
    if not s:
        return None
    lower = s.lower()

    # Explicit English
    if lower == "en" or lower.startswith("en-"):
        return "en"

    # Traditional Chinese markers (Windows: cht, zh-cht, zh-Hant, zh-TW, zh-HK)
    if any(
        tok in lower
        for tok in (
            "hant",
            "cht",
            "zh-tw",
            "zh-hk",
            "zh-mo",
            "zh-hant",
        )
    ):
        return "zh-HK"

    # Any Chinese → V1 uses zh-HK table (covers zh-CN/zh-SG as best effort)
    if lower == "zh" or lower.startswith("zh-") or lower.startswith("chi"):
        return "zh-HK"

    return None


def _windows_ui_language() -> str | None:
    """Windows: GetUserDefaultUILanguage → locale name (spec §42.5.1)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        # LOCALE_SNAME = 0x5c
        buf = ctypes.create_unicode_buffer(85)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if kernel32.GetLocaleInfoW(lang_id, 0x5C, buf, 85):
            return buf.value
        # Fallback: primary/sub language ids
        primary = lang_id & 0x3FF
        if primary == 0x04:  # LANG_CHINESE
            # SUBLANG_CHINESE_SIMPLIFIED=0x02, TRADITIONAL variants otherwise
            sub = (lang_id >> 10) & 0x3F
            if sub in (0x01, 0x03, 0x05):  # Traditional / Hong Kong / Macau
                return "zh-Hant"
            if sub == 0x02:
                return "zh-Hans"
            return "zh-Hant"
        if primary == 0x09:  # LANG_ENGLISH
            return "en"
    except Exception:
        return None
    return None


def detect_system_language() -> str:
    """Return 'zh-HK' or 'en'. Prefer real system UI language over process locale."""
    candidates: list[str] = []

    win = _windows_ui_language()
    if win:
        candidates.append(win)

    for getter in (
        lambda: locale.getlocale()[0],
        lambda: locale.getdefaultlocale()[0],  # type: ignore[deprecated]
    ):
        try:
            v = getter()
            if v:
                candidates.append(v)
        except Exception:
            pass

    for key in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        v = os.environ.get(key)
        if v:
            # LANGUAGE may be colon-separated list
            candidates.append(v.split(":")[0].split(".")[0])

    for raw in candidates:
        mapped = _normalize_to_ui_lang(raw)
        if mapped:
            return mapped

    return "en"


def set_language(lang: str) -> None:
    global _CURRENT
    mapped = _normalize_to_ui_lang(lang) or (lang if lang in _SUPPORTED else "en")
    if mapped not in _SUPPORTED:
        mapped = "en"
    _CURRENT = mapped
    _load(_CURRENT)


def current_language() -> str:
    return _CURRENT


def get(key: str, **kwargs) -> str:
    table = _load(_CURRENT)
    text = table.get(key)
    if text is None:
        text = _load("en").get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


# Auto-detect on import (overridden later by Settings if set)
set_language(detect_system_language())
