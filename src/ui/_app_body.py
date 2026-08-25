"""Main application window composition."""
from __future__ import annotations

import logging
from pathlib import Path

from src import i18n
from src.core.settings import AppSettings, load_settings
from src.core.storage import Storage
from src.glossary.store import GlossaryStore
from src.models.book import CanonicalBook
from src.queue.batch_queue import BatchQueue
from src.ui.paths import data_dir
from src.ui._common import _ctk, _t, log
from src.ui._mix_convert import ConvertMixin
from src.ui._mix_translate import TranslateMixin
from src.ui._mix_glossary import GlossaryMixin
from src.ui._mix_settings import SettingsMixin


class App(ConvertMixin, TranslateMixin, GlossaryMixin, SettingsMixin):
    def __init__(self, settings_path: Path | None = None) -> None:
        ctk = _ctk()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.settings_path = settings_path or (data_dir() / "settings.json")
        self.settings = load_settings(self.settings_path)
        iface = (self.settings.interface_language or "").strip()
        if iface not in ("en", "zh-Hant"):
            # First run / invalid: detect once, then persist explicit choice only
            iface = i18n.detect_system_language()
            if iface not in ("en", "zh-Hant"):
                iface = "en"
            self.settings.interface_language = iface
            try:
                from src.core.settings import save_settings

                save_settings(self.settings, self.settings_path)
            except Exception:
                pass
        i18n.set_language(iface)
        self.root = ctk.CTk()
        self.root.title(_t("app_title"))
        self.root.geometry("1024x720")
        self.db_path = data_dir() / "app.db"
        self.storage = Storage(self.db_path)
        self.glossary_store = GlossaryStore(data_dir() / "glossaries")
        self._preview_book: CanonicalBook | None = None
        self._preview_source: Path | None = None
        self._selected_chapter_id: str | None = None
        self._chapter_ids: list[str] = []
        self._queue: BatchQueue | None = None
        self._translate_inputs: list[Path] = []
        self._translate_output_dir: Path | None = None
        self._selected_glossary_id: str | None = None
        self._build_nav()
        self._pages: dict[str, object] = {}
        self._build_convert_page()
        self._build_translate_page()
        self._build_glossary_page()
