"""Translation-page language initialization must preserve strict validation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.queue.batch_queue import BatchQueue
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
