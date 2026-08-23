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
from src.core.pipeline import parse_to_book
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.models.blocks import BlockType
from src.models.book import CanonicalBook
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action
from src.ui.paths import assets_dir_for, data_dir, ebook_filetypes
from src.ui._common import _ctk, _t, _relaunch_process, log
from src.ui._common import (
    _INTERFACE_LANG_CODES,
    _SOURCE_LANG_CODES,
    _TARGET_LANG_CODES,
    _STYLE_CODES,
    _AFTER_CODES,
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

        self.drop_hint = ctk.CTkLabel(page, text=_t("drop_hint"), anchor="w")
        self.drop_hint.pack(fill="x", padx=4, pady=2)

        # Compact book information panel
        self.info_label = ctk.CTkLabel(
            page, text="", anchor="w", justify="left", font=("", 13)
        )
        self.info_label.pack(fill="x", padx=4, pady=4)

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(left, text=_t("chapter_detection"), font=("", 13, "bold")).pack(
            anchor="w"
        )
        self.chapter_list = ctk.CTkScrollableFrame(left)
        self.chapter_list.pack(fill="both", expand=True)
        self._chapter_buttons: list = []

        right = ctk.CTkFrame(body, width=200)
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

    def _enable_drag_drop(self) -> None:

        if sys.platform != "win32":
            return
        try:
            import windnd  # type: ignore

            def _on_drop(files):
                paths = []
                for f in files:
                    if isinstance(f, bytes):
                        try:
                            f = f.decode("utf-8")
                        except Exception:
                            f = f.decode(sys.getfilesystemencoding(), errors="replace")
                    paths.append(str(f))
                self.root.after(0, lambda: self._handle_dropped_paths(paths))

            windnd.hook_dropfiles(self.root, func=_on_drop)
            log.info("Drag-and-drop enabled (windnd)")
        except Exception as e:
            log.info("Drag-and-drop unavailable: %s", e)

    def _handle_dropped_paths(self, paths: list[str]) -> None:
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in (".epub", ".txt") and path.is_file():
                self._load_preview_path(path)
                return
        if paths:
            self._show_error(
                "error_open_file",
                _t("error_open_file", detail="unsupported file type"),
            )

    def _open_for_preview(self) -> None:
        try:
            path = filedialog.askopenfilename(
                parent=self.root,
                title=_t("open_file"),
                filetypes=ebook_filetypes(_t('filetypes_ebook'), _t('filetypes_epub'), _t('filetypes_all')),
            )
        except Exception as e:
            log.exception("filedialog failed")
            self._show_error("error_open_file", _t("error_open_file", detail=str(e)))
            return
        if not path:
            return
        self._load_preview_path(Path(path))

    def _load_preview_path(self, path: Path) -> None:

        path = Path(path)
        log.info("Loading for preview: %s", path)
        try:
            if not path.is_file():
                raise FileNotFoundError(str(path))
            assets = assets_dir_for(path)
            result = parse_to_book(path, assets_dir=assets)
        except Exception as e:
            log.exception("analyze failed for %s", path)
            detail = str(e) or type(e).__name__
            self._show_error("error_analyze", _t("error_analyze", detail=detail))
            self.convert_status.configure(text=_t("error_analyze", detail=detail))
            return

        self._preview_source = path
        self._preview_book = result.book
        self._selected_chapter_id = None
        self._update_book_info_panel()
        self._refresh_chapter_list()
        if result.warnings:
            self.convert_status.configure(
                text=_t("warnings_prefix", text="; ".join(result.warnings[:3]))
            )
        else:
            self.convert_status.configure(
                text=_t("loaded_file", name=self._preview_source.name)
            )
        self._show("convert")

    def _update_book_info_panel(self) -> None:
        if not self._preview_book:
            self.info_label.configure(text="")
            return
        meta = self._preview_book.metadata
        n_img = sum(
            1
            for ch in self._preview_book.chapters
            for b in ch.blocks
            if b.type == BlockType.IMAGE
        )
        text = (
            f"{_t('label_title')}: {meta.title}\n"
            f"{_t('label_author')}: {meta.author}\n"
            f"{_t('label_language')}: {meta.language}\n"
            f"{_t('label_chapter_count')}: {len(self._preview_book.chapters)}\n"
            f"{_t('label_image_count')}: {n_img}"
        )
        self.info_label.configure(text=text)

    def _refresh_chapter_list(self) -> None:

        ctk = _ctk()
        for w in self.chapter_list.winfo_children():
            w.destroy()
        self._chapter_buttons = []
        self._chapter_ids = []
        if not self._preview_book:
            return
        for ch in self._preview_book.chapters:
            self._chapter_ids.append(ch.id)
            label = _t(
                "chapter_row_compact",
                n=ch.order + 1,
                title=ch.title,
                blocks=len(ch.blocks),
            )
            selected = ch.id == self._selected_chapter_id
            btn = ctk.CTkButton(
                self.chapter_list,
                text=label,
                anchor="w",
                height=28,
                fg_color=("gray75", "gray25") if selected else ("gray90", "gray20"),
                text_color=("black", "white"),
                command=lambda cid=ch.id: self._select_chapter(cid),
            )
            btn.pack(fill="x", pady=1, padx=2)
            self._chapter_buttons.append(btn)
        self._update_book_info_panel()

    def _select_chapter(self, chapter_id: str) -> None:
        self._selected_chapter_id = chapter_id
        self._refresh_chapter_list()

    def _require_book_and_selection(self) -> str | None:
        if not self._preview_book:
            messagebox.showinfo(_t("info"), _t("open_file_first"), parent=self.root)
            return None
        if not self._selected_chapter_id:
            messagebox.showinfo(_t("info"), _t("select_chapter"), parent=self.root)
            return None
        return self._selected_chapter_id

    def _op_merge(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ids = [c.id for c in self._preview_book.chapters]
        try:
            idx = ids.index(cid)
        except ValueError:
            return
        if idx + 1 >= len(ids):
            messagebox.showinfo(_t("info"), _t("no_next_chapter"), parent=self.root)
            return
        try:
            self._preview_book = merge_adjacent(
                self._preview_book, cid, ids[idx + 1]
            )
            self._selected_chapter_id = cid
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("merged_next"))
        except ChapterOpError as e:
            self._show_error("error", str(e))

    def _op_split(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch or len(ch.blocks) < 2:
            messagebox.showinfo(_t("info"), _t("split_need_blocks"), parent=self.root)
            return
        mid = len(ch.blocks) // 2
        at_id = ch.blocks[mid].id
        try:
            self._preview_book = split_chapter(self._preview_book, cid, at_id)
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("split_at_block", block_id=at_id))
        except ChapterOpError as e:
            self._show_error("error", str(e))

    def _op_rename(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch:
            return
        new_title = simpledialog.askstring(
            _t("rename_title"),
            _t("rename_prompt"),
            initialvalue=ch.title,
            parent=self.root,
        )
        if not new_title:
            return
        try:
            self._preview_book = rename_chapter(
                self._preview_book, cid, new_title
            )
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("renamed"))
        except ChapterOpError as e:
            self._show_error("error", str(e))

    def _op_remove(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        if not messagebox.askyesno(
            _t("confirm"), _t("remove_chapter_q"), parent=self.root
        ):
            return
        try:
            self._preview_book = remove_chapter(self._preview_book, cid)
            self._selected_chapter_id = None
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("chapter_removed"))
        except ChapterOpError as e:
            self._show_error("error", str(e))

    def _do_convert(self) -> None:
        if not self._preview_book:
            messagebox.showinfo(
                _t("info"), _t("open_analyze_first"), parent=self.root
            )
            return
        try:
            out = filedialog.asksaveasfilename(
                parent=self.root,
                defaultextension=".epub",
                filetypes=[(_t("filetypes_epub"), "*.epub")],
                initialfile=(
                    f"{self._preview_source.stem}.epub"
                    if self._preview_source
                    else "output.epub"
                ),
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not out:
            return
        try:
            generate_epub(self._preview_book, out)
        except Exception as e:
            log.exception("generate_epub failed")
            self._show_error("error", str(e))
            return
        self.convert_status.configure(text=_t("wrote_file", path=out))
        messagebox.showinfo(_t("done"), _t("wrote_file", path=out), parent=self.root)

    def _send_preview_to_translate(self) -> None:

        if not self._preview_book:
            messagebox.showinfo(
                _t("info"), _t("open_analyze_first"), parent=self.root
            )
            return
        try:
            out = filedialog.askdirectory(parent=self.root, title=_t("output_folder"))
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not out:
            return
        self._translate_output_dir = Path(out)
        # Ensure queue exists with current settings
        self._ensure_queue()
        assert self._queue is not None
        src_name = (
            self._preview_source.name if self._preview_source else "normalized.epub"
        )
        stem = Path(src_name).stem
        # Deep-copy book so further Preview edits do not mutate queued snapshot
        book_snap = CanonicalBook.model_validate(self._preview_book.model_dump())
        item = self._queue.add(
            self._preview_source or Path(src_name),
            self._translate_output_dir / f"{stem}.translated.epub",
            book=book_snap,
            display_name=book_snap.metadata.title or stem,
        )
        self._refresh_queue_list()
        self.translate_log.insert(
            "end",
            _t("queued_normalized", title=book_snap.metadata.title or stem) + "\n",
        )
        self._show("translate")
        messagebox.showinfo(
            _t("info"),
            _t("queued_normalized", title=book_snap.metadata.title or stem),
            parent=self.root,
        )
        return item

    def _ensure_queue(self) -> BatchQueue:
        if self._queue is not None:
            return self._queue
        cfg = self._job_config_from_settings()
        gloss_entries: list[dict[str, str]] = []
        if getattr(self, "_selected_glossary_id", None):
            try:
                g = self.glossary_store.load(self._selected_glossary_id)
                gloss_entries = g.as_prompt_list(only_confirmed=True)
                cfg = cfg.model_copy(
                    update={"glossary_version": g.version}
                )
            except Exception:
                log.exception("load glossary for queue")
        self._queue = BatchQueue(
            storage=self.storage,
            work_root=data_dir() / "jobs",
            config=cfg,
            glossary=gloss_entries,
            on_progress=self._queue_progress,
        )
        return self._queue

    def _job_config_from_settings(self) -> JobConfig:
        return JobConfig(
            source_language=self.settings.translation.source_language,
            target_language=self.settings.translation.target_language,
            endpoint=self.settings.ai.endpoint,
            model=self.settings.ai.model,
            model_identifier=self.settings.ai.model_identifier
            or self.settings.ai.model,
            style=self.settings.translation.style,
            chunk_target_tokens=self.settings.translation.chunk_target_tokens,
            carry_over_paragraphs=self.settings.translation.carry_over_paragraphs,
            retry_count=self.settings.ai.retry_count,
            retry_delay_seconds=self.settings.ai.retry_delay_seconds,
            request_timeout_seconds=self.settings.ai.timeout_seconds,
            request_interval_seconds=self.settings.ai.request_interval_seconds,
            endpoint_fail_threshold=self.settings.ai.endpoint_fail_threshold,
            prompt=self.settings.translation.prompt or None,
        )
