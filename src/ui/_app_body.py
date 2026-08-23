"""Main application window composition."""
from __future__ import annotations

import logging
from pathlib import Path

from src import i18n
from src.core.settings import AppSettings
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
        self.settings = AppSettings.load(self.settings_path)
        if self.settings.interface_language:
            i18n.set_language(self.settings.interface_language)
        else:
            i18n.set_language(i18n.detect_system_language())
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
        self._enable_drag_drop()
        self._show("convert")

    def _show_error(self, title_key: str, detail: str) -> None:
        from tkinter import messagebox
        log.error("%s: %s", title_key, detail)
        try:
            messagebox.showerror(_t("error"), detail, parent=self.root)
        except Exception:
            messagebox.showerror("Error", detail)

    def _build_nav(self) -> None:
        ctk = _ctk()
        nav = ctk.CTkFrame(self.root, width=180)
        nav.pack(side="left", fill="y", padx=8, pady=8)
        for key, label_key in [
            ("convert", "convert"),
            ("translate", "translate"),
            ("glossary", "glossary"),
        ]:
            ctk.CTkButton(
                nav, text=_t(label_key), command=lambda k=key: self._show(k),
            ).pack(fill="x", pady=4, padx=8)
        ctk.CTkButton(
            nav, text=_t("settings"), command=self._open_settings
        ).pack(fill="x", pady=4, padx=8, side="bottom")
        self.content = ctk.CTkFrame(self.root)
        self.content.pack(side="right", fill="both", expand=True, padx=8, pady=8)

    def _show(self, name: str) -> None:
        for p in self._pages.values():
            p.pack_forget()
        self._pages[name].pack(fill="both", expand=True)

    def run(self) -> None:
        self.root.mainloop()


def launch() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    App().run()


if __name__ == "__main__":
    launch()
