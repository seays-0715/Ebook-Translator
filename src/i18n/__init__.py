"""Key-based i18n. V1: zh-HK / zh-TW + en. Fallback: en."""

from __future__ import annotations

import json
import locale
from pathlib import Path

_DIR = Path(__file__).parent
_CACHE: dict[str, dict[str, str]] = {}
_CURRENT = "en"


def _load(lang: str) -> dict[str, str]:
    if lang in _CACHE:
        return _CACHE[lang]
    path = _DIR / f"{lang}.json"
    if not path.exists():
        # try base
        base = lang.split("-")[0]
        path = _DIR / f"{base}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    _CACHE[lang] = data
    return data


def detect_system_language() -> str:
    try:
        lang, _ = locale.getdefaultlocale()
        if not lang:
            return "en"
        lang = lang.replace("_", "-")
        if lang.startswith("zh"):
            if "TW" in lang or "HK" in lang or "Hant" in lang:
                return "zh-HK"
            return "zh-HK"  # V1 maps all zh to zh-HK tables
        if lang.startswith("en"):
            return "en"
        return "en"
    except Exception:
        return "en"


def set_language(lang: str) -> None:
    global _CURRENT
    _CURRENT = lang
    _load(lang)


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


# Auto-detect on import
set_language(detect_system_language())
