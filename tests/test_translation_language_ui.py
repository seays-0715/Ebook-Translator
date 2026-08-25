"""Translation-page language initialization must preserve strict validation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ui._mix_translate import TranslateMixin


class _Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def _config(source: str, target: str):
    page = object.__new__(TranslateMixin)
    page.settings = SimpleNamespace(translation=SimpleNamespace(style="fiction"))
    page._tr_src_var = _Var(source)
    page._tr_tgt_var = _Var(target)
    page._tr_style_var = _Var("Fiction")
    page._tr_style_l2c = {"Fiction": "fiction", "Non-Fiction": "nonfiction"}
    return page


def test_invalid_persisted_source_is_not_substituted():
    page = _config("not-a-language", "Traditional Chinese")
    with pytest.raises(ValueError, match="Unsupported language code"):
        page._translation_page_config()


def test_invalid_persisted_target_is_not_substituted():
    page = _config("Japanese", "not-a-language")
    with pytest.raises(ValueError, match="Unsupported language code"):
        page._translation_page_config()


def test_translation_page_contains_no_ja_or_zh_hant_initialization_fallbacks():
    source = Path("src/ui/_mix_translate.py").read_text(encoding="utf-8")
    assert 'except ValueError:\n            src_code = "ja"' not in source
    assert 'except ValueError:\n            tgt_code = "zh-Hant"' not in source


def test_invalid_language_never_reaches_job_config():
    page = _config("auto", "Traditional Chinese")
    with pytest.raises(ValueError):
        page._translation_page_config()


def test_invalid_persisted_source_selector_label_is_empty_not_ja():
    label, err = TranslateMixin._selection_label_for_persisted_language("not-a-language")
    assert label == ""
    assert err is not None
    assert "not-a-language" in err or "Unsupported" in err
    # Must not silently become Japanese
    assert label != "Japanese"
    assert "ja" not in label.lower()


def test_invalid_persisted_target_selector_label_is_empty_not_zh_hant():
    label, err = TranslateMixin._selection_label_for_persisted_language("totally-bogus")
    assert label == ""
    assert err is not None
    assert label != "Traditional Chinese"
    assert "zh-Hant" not in label


def test_valid_persisted_language_loads_normally():
    label, err = TranslateMixin._selection_label_for_persisted_language("en")
    assert err is None
    assert label == "English"
    label2, err2 = TranslateMixin._selection_label_for_persisted_language("zh-Hant")
    assert err2 is None
    assert label2 == "Traditional Chinese"


def test_empty_selector_blocks_start_via_page_config():
    page = _config("", "Traditional Chinese")
    with pytest.raises(ValueError):
        page._translation_page_config()


def test_start_blocked_while_source_invalid():
    page = _config("not-a-language", "English")
    with pytest.raises(ValueError):
        page._translation_page_config()


def test_build_page_logic_does_not_embed_invalid_code_as_label():
    """Source of truth for UI init: invalid code → empty label, not the raw code."""
    from src.core.languages import normalize_code
    from src.ui._common import language_code_to_label

    raw = "xx-INVALID"
    try:
        code = normalize_code(raw)
        label = language_code_to_label(code)
    except ValueError:
        code = None
        label = ""
    assert code is None
    assert label == ""
    assert label != "Japanese"
    assert label != "Traditional Chinese"
    assert label != raw


def test_no_invalid_translation_language_configuration_banner():
    """User-facing UI must not show developer configuration error text."""
    source = Path("src/ui/_mix_translate.py").read_text(encoding="utf-8")
    assert "Invalid translation language configuration" not in source
    assert "_translation_config_error" not in source


def test_language_selector_labels_exclude_internal_aliases():
    from src.ui._common import language_display_labels

    labels = language_display_labels()
    joined = " | ".join(labels)
    assert "zh-TW" not in joined
    assert "zh-HK" not in joined
    assert "zh-Hant" not in joined  # registry code, not display name
    assert "Traditional Chinese" in labels
    assert "Auto Detect" not in labels
    assert "auto" not in {x.lower() for x in labels}
