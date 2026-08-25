"""Convert page operations and job wiring (split for packaging size)."""
from __future__ import annotations

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
from src.epub.generator import generate_epub
from src.models.book import CanonicalBook
from src.models.job import JobConfig
from src.queue.batch_queue import BatchQueue
from src.ui.paths import data_dir
from src.ui._common import _CONVERSION_MODE_CODES, _t, log


class ConvertOpsMixin:
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
        from src.ui.paths import resolve_output_dir

        out_dir = resolve_output_dir(
            getattr(self.settings.output, "default_dir", None)
        )
        initial = (
            f"{self._preview_source.stem}.epub"
            if self._preview_source
            else "output.epub"
        )
        try:
            out = filedialog.asksaveasfilename(
                parent=self.root,
                defaultextension=".epub",
                filetypes=[(_t("filetypes_epub"), "*.epub")],
                initialdir=str(out_dir),
                initialfile=initial,
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not out:
            return
        try:
            generate_epub(
                self._preview_book, out, conversion_mode=self._current_conversion_mode()
            )
        except Exception as e:
            log.exception("generate_epub failed")
            self._show_error("error", str(e))
            return
        self.convert_status.configure(text=_t("wrote_file", path=out))
        messagebox.showinfo(_t("done"), _t("wrote_file", path=out), parent=self.root)

    def _resolved_output_dir(self) -> Path:
        from src.ui.paths import resolve_output_dir

        return resolve_output_dir(getattr(self.settings.output, "default_dir", None))

    def _send_preview_to_translate(self) -> None:

        if not self._preview_book:
            messagebox.showinfo(
                _t("info"), _t("open_analyze_first"), parent=self.root
            )
            return
        self._translate_output_dir = self._resolved_output_dir()
        self._ensure_queue()
        assert self._queue is not None
        src_name = (
            self._preview_source.name if self._preview_source else "normalized.epub"
        )
        stem = Path(src_name).stem
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
        """Build JobConfig snapshot for new jobs.

        Source / Target / Style / Prompt come from Translation page when available
        (task config). AI connection and chunk params remain global Settings.
        Once the Job is created, this snapshot is frozen.
        """
        from src.translation.prompts import resolve_system_prompt

        if hasattr(self, "_translation_page_config"):
            src, tgt, style = self._translation_page_config()
        else:
            src = normalize_code(
                self.settings.translation.source_language or "ja"
            )
            tgt = normalize_code(
                self.settings.translation.target_language or "zh-Hant"
            )
            style = (self.settings.translation.style or "fiction").lower()
            style = "nonfiction" if "non" in style else "fiction"

        custom = ""
        if hasattr(self, "_read_translate_prompt"):
            custom = self._read_translate_prompt() or ""
        if not custom.strip():
            if style == "nonfiction":
                custom = getattr(self.settings.translation, "nonfiction_prompt", "") or ""
            else:
                custom = getattr(self.settings.translation, "fiction_prompt", "") or ""
        prompt = resolve_system_prompt(style, custom or None)
        return JobConfig(
            source_language=normalize_code(src),
            target_language=normalize_code(tgt),
            endpoint=self.settings.ai.endpoint,
            model=self.settings.ai.model,
            model_identifier=self.settings.ai.model_identifier
            or self.settings.ai.model,
            style=style,
            chunk_target_tokens=self.settings.translation.chunk_target_tokens,
            carry_over_paragraphs=self.settings.translation.carry_over_paragraphs,
            retry_count=self.settings.ai.retry_count,
            retry_delay_seconds=self.settings.ai.retry_delay_seconds,
            request_timeout_seconds=self.settings.ai.timeout_seconds,
            request_interval_seconds=self.settings.ai.request_interval_seconds,
            endpoint_fail_threshold=self.settings.ai.endpoint_fail_threshold,
            prompt=prompt,
        )

    def _current_conversion_mode(self) -> str:
        label = ""
        try:
            label = self._conversion_mode_var.get()
        except Exception:
            pass
        for code in _CONVERSION_MODE_CODES:
            if label == _t(f"conversion_mode_{code}"):
                return code
        fallback = getattr(self.settings.output, "conversion_mode", None) or "standard"
        if fallback in _CONVERSION_MODE_CODES:
            return fallback
        return "standard"
