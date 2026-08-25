"""UI mixin."""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from src.core.chapter_ops import (
    ChapterOpError,
    merge_adjacent,
    remove_chapter,
    rename_chapter,
    split_chapter,
)
from src.core.languages import normalize_code
from src.core.pipeline import parse_to_book
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.models.blocks import BlockType
from src.models.book import CanonicalBook
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action
from src.ui.paths import assets_dir_for, data_dir, ebook_filetypes
from src.ui._common import (
    _CONVERSION_MODE_CODES,
    _ctk,
    _t,
    _relaunch_process,
    format_chapter_list_label,
    log,
)

class ConvertMixin:
    def _build_convert_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["convert"] = page

        top = ctk.CTkFrame(page)
        top.pack(fill="x", pady=4)
        ctk.CTkButton(top, text=_t("open_file"), command=self._open_for_preview).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            top, text=_t("confirm_convert"), command=self._do_convert
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            top, text=_t("send_to_translate"), command=self._send_preview_to_translate
        ).pack(side="left", padx=4)

        mode_row = ctk.CTkFrame(page)
        mode_row.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(mode_row, text=_t("label_conversion_mode")).pack(side="left", padx=4)
        mode_labels = [_t(f"conversion_mode_{c}") for c in _CONVERSION_MODE_CODES]
        self._conversion_mode_var = ctk.StringVar(
            value=_t(f"conversion_mode_{getattr(self.settings.output, 'conversion_mode', 'standard')}")
        )
        self._conversion_mode_menu = ctk.CTkOptionMenu(
            mode_row,
            values=mode_labels,
            variable=self._conversion_mode_var,
            width=220,
            command=self._on_conversion_mode_changed,
        )
        self._conversion_mode_menu.pack(side="left", padx=4)

        self.drop_hint = ctk.CTkLabel(page, text=_t("drop_hint"), anchor="w")
        self.drop_hint.pack(fill="x", padx=4, pady=2)

        self.info_label = ctk.CTkLabel(
            page, text="", anchor="w", justify="left", font=("", 13)
        )
        self.info_label.pack(fill="x", padx=4, pady=4)

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(body, width=240)
        left.pack(side="left", fill="y", padx=(0, 4))
        left.pack_propagate(False)
        ctk.CTkLabel(left, text=_t("chapter_detection"), font=("", 13, "bold")).pack(
            anchor="w"
        )
        self.chapter_list = ctk.CTkScrollableFrame(left)
        self.chapter_list.pack(fill="both", expand=True)
        self._chapter_buttons: list = []

        center = ctk.CTkFrame(body)
        center.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(center, text=_t("content_preview"), font=("", 13, "bold")).pack(
            anchor="w"
        )
        self.chapter_preview_title = ctk.CTkLabel(
            center, text="", anchor="w", font=("", 14, "bold")
        )
        self.chapter_preview_title.pack(fill="x", pady=(2, 4))
        self.chapter_preview = ctk.CTkTextbox(center, font=("", 13), wrap="word")
        self.chapter_preview.pack(fill="both", expand=True)
        self.chapter_preview.configure(state="disabled")

        right = ctk.CTkFrame(body, width=140)
        right.pack(side="right", fill="y", padx=(4, 0))
        for text_key, cmd in [
            ("merge", self._op_merge),
            ("split", self._op_split),
            ("rename", self._op_rename),
            ("remove", self._op_remove),
        ]:
            ctk.CTkButton(right, text=_t(text_key), command=cmd).pack(
                fill="x", pady=4, padx=8
            )

        self.convert_status = ctk.CTkLabel(page, text="", anchor="w")
        self.convert_status.pack(fill="x", pady=4)
