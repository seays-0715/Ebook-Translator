"""Strict language registry and normalize_code behavior."""

from __future__ import annotations

import pytest

from src.core.languages import (
    LANGUAGES,
    normalize_code,
    code_to_name,
    name_to_code,
)


def test_registry_count():
    assert len(LANGUAGES) == 38


def test_normalize_known():
    assert normalize_code("ja") == "ja"
    assert normalize_code("zh-Hant") == "zh-Hant"
    assert normalize_code("en") == "en"


def test_normalize_aliases():
    assert normalize_code("zh-TW") == "zh-Hant"
    assert normalize_code("zh-HK") == "zh-Hant"
    assert normalize_code("zh-CN") == "zh"
    assert normalize_code("zh-Hans") == "zh"


def test_normalize_rejects_auto():
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code("auto")


def test_normalize_rejects_empty():
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code("")
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code("   ")


def test_normalize_rejects_none():
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code(None)


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code("完全亂打嘅字串")
    with pytest.raises(ValueError, match="Unsupported language code"):
        normalize_code("xx-unknown")


def test_no_silent_fallback_to_ja():
    with pytest.raises(ValueError):
        normalize_code("auto")
    with pytest.raises(ValueError):
        normalize_code("not-a-lang")


def test_code_to_name():
    assert code_to_name("ja") == "Japanese"
    assert code_to_name("zh-Hant") == "Traditional Chinese"


def test_name_to_code():
    assert name_to_code("Japanese") == "ja"
    assert name_to_code("Traditional Chinese") == "zh-Hant"
    assert name_to_code("not-real") is None
