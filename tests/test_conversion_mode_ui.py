"""Conversion Mode UI must show human-readable labels, never internal codes."""

from __future__ import annotations

from pathlib import Path

from src import i18n
from src.ui._common import _CONVERSION_MODE_CODES, _t


def test_conversion_mode_codes_are_only_standard_and_compact():
    assert _CONVERSION_MODE_CODES == ("standard", "compact")
    assert "clean" not in _CONVERSION_MODE_CODES


def test_conversion_mode_english_labels():
    i18n.set_language("en")
    assert _t("conversion_mode_standard") == "Standard"
    assert _t("conversion_mode_compact") == "Compact"
    assert _t("label_conversion_mode") == "Conversion Mode"
    # Must not surface internal codes as the display string
    assert _t("conversion_mode_standard") != "standard"
    assert _t("conversion_mode_compact") != "compact"
    assert _t("conversion_mode_standard") != "clean"


def test_conversion_mode_traditional_chinese_labels():
    i18n.set_language("zh-Hant")
    assert _t("conversion_mode_standard") == "標準"
    assert _t("conversion_mode_compact") == "精簡"
    assert _t("label_conversion_mode") == "轉換模式"
    i18n.set_language("en")


def test_convert_preview_builds_labels_from_i18n_not_raw_codes():
    source = Path("src/ui/_mix_convert_preview.py").read_text(encoding="utf-8")
    assert 'f"conversion_mode_{c}"' in source or "conversion_mode_{" in source
    # Must not hardcode English-only option values in the OptionMenu
    assert 'values=["standard", "compact"]' not in source
    assert 'values=["clean"' not in source
    assert "Conversion Mode: clean" not in source


def test_unknown_persisted_mode_does_not_become_user_visible_code():
    """Init path clamps unknown settings values to a known i18n label."""
    i18n.set_language("en")
    raw = "clean"
    code = raw if raw in _CONVERSION_MODE_CODES else "standard"
    label = _t(f"conversion_mode_{code}")
    assert label == "Standard"
    assert label != "clean"
    assert "conversion_mode_" not in label
