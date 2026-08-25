"""Translate-page prompt Save / Reset helpers (kept separate for packaging)."""
from __future__ import annotations

from tkinter import messagebox

from src.core.settings import save_settings
from src.translation.prompts import default_prompt_for_style
from src.ui._common import _t, log


class TranslatePromptSaveMixin:
    """Explicit Save / Reset for Fiction / Non-Fiction prompts."""

    def _reset_translate_prompt(self) -> None:
        try:
            _, _, style = self._translation_page_config()
        except Exception:
            style = "fiction"
        box = getattr(self, "_tr_prompt_box", None)
        if box is None:
            return
        box.delete("1.0", "end")
        box.insert("1.0", default_prompt_for_style(style))
        try:
            self._persist_translate_prompt(style, "")
            save_settings(self.settings, self.settings_path)
        except Exception:
            log.exception("persist reset prompt")

    def _save_translate_prompt(self) -> None:
        try:
            _, _, style = self._translation_page_config()
        except Exception:
            style = "fiction"
        text = self._read_translate_prompt()
        try:
            self._persist_translate_prompt(style, text)
            save_settings(self.settings, self.settings_path)
            messagebox.showinfo(_t("info"), _t("prompt_saved"), parent=self.root)
        except Exception as e:
            log.exception("save translate prompt")
            self._show_error("error", str(e))
