"""Main application window — Convert / Translate / Glossary + Settings.

Convert page supports Chapter Preview ops: Merge / Split / Rename / Remove.
All user-visible strings go through i18n (spec §42.5).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore

from src import i18n
from src.core.chapter_ops import (
    ChapterOpError,
    merge_adjacent,
    remove_chapter,
    rename_chapter,
    split_chapter,
)
from src.core.pipeline import parse_to_book
from src.core.settings import AppSettings
from src.core.storage import Storage
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.glossary.store import GlossaryStore
from src.models.book import CanonicalBook
from src.models.job import JobConfig
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action


def _ctk():
    if ctk is None:
        raise RuntimeError(
            "customtkinter is not installed. Run: pip install customtkinter"
        )
    return ctk


def _t(key: str, **kwargs) -> str:
    return i18n.get(key, **kwargs)


class App:
    def __init__(self, settings_path: Path | None = None) -> None:
        ctk = _ctk()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.settings_path = (
            settings_path or Path.home() / ".ebook_translator" / "settings.json"
        )
        self.settings = AppSettings.load(self.settings_path)
        if self.settings.interface_language:
            i18n.set_language(self.settings.interface_language)

        self.root = ctk.CTk()
        self.root.title(_t("app_title"))
        self.root.geometry("1024x720")

        self.db_path = Path.home() / ".ebook_translator" / "app.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage = Storage(self.db_path)
        self.glossary_store = GlossaryStore(
            Path.home() / ".ebook_translator" / "glossaries"
        )

        self._preview_book: CanonicalBook | None = None
        self._preview_source: Path | None = None
        self._selected_chapter_id: str | None = None
        self._chapter_ids: list[str] = []

        self._queue: BatchQueue | None = None
        self._translate_inputs: list[Path] = []
        self._translate_output_dir: Path | None = None
        self._progress_book_name: str = ""
        self._progress_chapter_cur: int = 0
        self._progress_chapter_total: int = 0

        self._build_nav()
        self._pages: dict[str, object] = {}
        self._build_convert_page()
        self._build_translate_page()
        self._build_glossary_page()
        self._show("convert")

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
                nav,
                text=_t(label_key),
                command=lambda k=key: self._show(k),
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

    # ================================================================= Convert
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

        self.info_label = ctk.CTkLabel(page, text="", anchor="w", justify="left")
        self.info_label.pack(fill="x", padx=4, pady=4)

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(left, text=_t("chapters")).pack(anchor="w")
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

    def _open_for_preview(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                (_t("filetypes_ebook"), "*.epub *.txt"),
                (_t("filetypes_all"), "*.*"),
            ]
        )
        if not path:
            return
        self._preview_source = Path(path)
        result = parse_to_book(self._preview_source)
        self._preview_book = result.book
        self._selected_chapter_id = None
        self._refresh_chapter_list()
        meta = result.book.metadata
        self.info_label.configure(
            text=_t(
                "book_info",
                title=meta.title,
                author=meta.author,
                language=meta.language,
                chapters=len(result.book.chapters),
            )
        )
        if result.warnings:
            self.convert_status.configure(
                text=_t("warnings_prefix", text="; ".join(result.warnings[:3]))
            )
        else:
            self.convert_status.configure(
                text=_t("loaded_file", name=self._preview_source.name)
            )

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
                "chapter_row",
                n=ch.order + 1,
                title=ch.title,
                blocks=len(ch.blocks),
            )
            selected = ch.id == self._selected_chapter_id
            btn = ctk.CTkButton(
                self.chapter_list,
                text=label,
                anchor="w",
                fg_color=("gray75", "gray25") if selected else ("gray90", "gray20"),
                text_color=("black", "white"),
                command=lambda cid=ch.id: self._select_chapter(cid),
            )
            btn.pack(fill="x", pady=2, padx=2)
            self._chapter_buttons.append(btn)

    def _select_chapter(self, chapter_id: str) -> None:
        self._selected_chapter_id = chapter_id
        self._refresh_chapter_list()

    def _require_book_and_selection(self) -> str | None:
        if not self._preview_book:
            messagebox.showinfo(_t("info"), _t("open_file_first"))
            return None
        if not self._selected_chapter_id:
            messagebox.showinfo(_t("info"), _t("select_chapter"))
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
            messagebox.showinfo(_t("info"), _t("no_next_chapter"))
            return
        try:
            self._preview_book = merge_adjacent(
                self._preview_book, cid, ids[idx + 1]
            )
            self._selected_chapter_id = cid
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("merged_next"))
        except ChapterOpError as e:
            messagebox.showerror(_t("error"), str(e))

    def _op_split(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch or len(ch.blocks) < 2:
            messagebox.showinfo(_t("info"), _t("split_need_blocks"))
            return
        mid = len(ch.blocks) // 2
        at_id = ch.blocks[mid].id
        try:
            self._preview_book = split_chapter(self._preview_book, cid, at_id)
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("split_at_block", block_id=at_id))
        except ChapterOpError as e:
            messagebox.showerror(_t("error"), str(e))

    def _op_rename(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch:
            return
        new_title = simpledialog.askstring(
            _t("rename_title"), _t("rename_prompt"), initialvalue=ch.title
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
            messagebox.showerror(_t("error"), str(e))

    def _op_remove(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        if not messagebox.askyesno(_t("confirm"), _t("remove_chapter_q")):
            return
        try:
            self._preview_book = remove_chapter(self._preview_book, cid)
            self._selected_chapter_id = None
            self._refresh_chapter_list()
            self.convert_status.configure(text=_t("chapter_removed"))
        except ChapterOpError as e:
            messagebox.showerror(_t("error"), str(e))

    def _do_convert(self) -> None:
        if not self._preview_book:
            messagebox.showinfo(_t("info"), _t("open_analyze_first"))
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".epub",
            filetypes=[(_t("filetypes_epub"), "*.epub")],
            initialfile=(
                f"{self._preview_source.stem}.epub"
                if self._preview_source
                else "output.epub"
            ),
        )
        if not out:
            return
        generate_epub(self._preview_book, out)
        self.convert_status.configure(text=_t("wrote_file", path=out))
        messagebox.showinfo(_t("done"), _t("wrote_file", path=out))

    # =============================================================== Translate
    def _build_translate_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["translate"] = page

        row = ctk.CTkFrame(page)
        row.pack(fill="x", pady=4)
        ctk.CTkButton(row, text=_t("add_books"), command=self._add_translate).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row, text=_t("start_translation"), command=self._start_queue
        ).pack(side="left", padx=4)
        ctk.CTkButton(row, text=_t("pause"), command=self._pause_queue).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text=_t("resume"), command=self._resume_queue).pack(
            side="left", padx=4
        )

        # Spec §41 progress: Book / Chapter / Chunk / Overall
        prog = ctk.CTkFrame(page)
        prog.pack(fill="x", padx=4, pady=4)
        self.lbl_book = ctk.CTkLabel(prog, text=_t("progress_book", book="-"), anchor="w")
        self.lbl_book.pack(fill="x")
        self.lbl_chapter = ctk.CTkLabel(
            prog, text=_t("progress_chapter", current=0, total=0), anchor="w"
        )
        self.lbl_chapter.pack(fill="x")
        self.lbl_chunk = ctk.CTkLabel(
            prog, text=_t("progress_chunk", current=0, total=0), anchor="w"
        )
        self.lbl_chunk.pack(fill="x")
        self.lbl_overall = ctk.CTkLabel(
            prog, text=_t("progress_overall", percent=0), anchor="w"
        )
        self.lbl_overall.pack(fill="x")
        self.progress_label = ctk.CTkLabel(prog, text=_t("idle"), anchor="w")
        self.progress_label.pack(fill="x")
        self.progress_bar = ctk.CTkProgressBar(prog)
        self.progress_bar.pack(fill="x", padx=0, pady=4)
        self.progress_bar.set(0)

        self.translate_log = ctk.CTkTextbox(page, font=("Consolas", 13))
        self.translate_log.pack(fill="both", expand=True, pady=8)

    def _add_translate(self) -> None:
        paths = filedialog.askopenfilenames(
            filetypes=[
                (_t("filetypes_ebook"), "*.epub *.txt"),
                (_t("filetypes_all"), "*.*"),
            ]
        )
        self._translate_inputs = [Path(p) for p in paths]
        out = filedialog.askdirectory(title=_t("output_folder"))
        if out:
            self._translate_output_dir = Path(out)
        self.translate_log.insert(
            "end", _t("queued_books", count=len(self._translate_inputs)) + "\n"
        )

    def _start_queue(self) -> None:
        if not self._translate_inputs or not self._translate_output_dir:
            messagebox.showinfo(_t("info"), _t("add_books_output_first"))
            return
        cfg = JobConfig(
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

        def on_progress(event, data):
            def ui():
                if event == "chunk_done":
                    total = max(int(data.get("total") or 1), 1)
                    completed = int(data.get("completed") or 0)
                    failed = int(data.get("failed") or 0)
                    done = completed + failed
                    pct = int(100 * done / total)
                    self.progress_bar.set(done / total)
                    self.lbl_chunk.configure(
                        text=_t(
                            "progress_chunk",
                            current=done,
                            total=total,
                        )
                    )
                    self.lbl_overall.configure(
                        text=_t("progress_overall", percent=pct)
                    )
                    job_id = str(data.get("job_id", ""))[:8]
                    self.progress_label.configure(
                        text=_t(
                            "progress_job_line",
                            job_id=job_id,
                            completed=completed,
                            total=total,
                            status=data.get("status"),
                        )
                    )
                    # Best-effort chapter counters from job book
                    if self._queue and data.get("job_id"):
                        try:
                            job = self.storage.load_job(data["job_id"])
                            nch = len(job.book.chapters)
                            self._progress_chapter_total = nch
                            self.lbl_book.configure(
                                text=_t(
                                    "progress_book",
                                    book=job.book.metadata.title or job_id,
                                )
                            )
                            # Approximate chapter from completed ratio
                            cur_ch = min(
                                nch,
                                max(1, int(round(done / total * nch))) if nch else 0,
                            )
                            self.lbl_chapter.configure(
                                text=_t(
                                    "progress_chapter",
                                    current=cur_ch,
                                    total=nch,
                                )
                            )
                        except Exception:
                            pass
                    self.translate_log.insert(
                        "end",
                        f"[{completed}/{total}] {data.get('status')}\n",
                    )
                    self.translate_log.see("end")
                elif event == "item_exported":
                    self.translate_log.insert(
                        "end",
                        _t("progress_exported", path=data.get("output")) + "\n",
                    )
                elif event == "queue_finished":
                    self.progress_label.configure(text=_t("queue_finished"))
                    out_dir = self._translate_output_dir
                    after_completion_action(
                        self.settings.output.after_completion,
                        output_folder=out_dir,
                    )

            self.root.after(0, ui)

        q = BatchQueue(
            storage=self.storage,
            work_root=Path.home() / ".ebook_translator" / "jobs",
            config=cfg,
            on_progress=on_progress,
        )
        for p in self._translate_inputs:
            q.add(p, self._translate_output_dir / f"{p.stem}.translated.epub")
        self._queue = q
        if self._translate_inputs:
            self.lbl_book.configure(
                text=_t(
                    "progress_book",
                    book=self._translate_inputs[0].name,
                )
            )
        q.start()
        self.translate_log.insert("end", _t("queue_started") + "\n")
        threading.Thread(target=self._watch_queue, daemon=True).start()

    def _watch_queue(self) -> None:
        while self._queue and self._queue.status.value == "running":
            time.sleep(0.5)
            w = self._queue._worker
            if w and not w.is_alive():
                break
        if self._queue:
            self._queue.emit(
                "queue_finished",
                {"status": self._queue.status.value},
            )

    def _pause_queue(self) -> None:
        if self._queue:
            self._queue.pause()
            self.translate_log.insert("end", _t("pause_requested") + "\n")

    def _resume_queue(self) -> None:
        if self._queue:
            self._queue.resume()
            self.translate_log.insert("end", _t("resume_log") + "\n")
            threading.Thread(target=self._watch_queue, daemon=True).start()

    # ================================================================ Glossary
    def _build_glossary_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["glossary"] = page
        row = ctk.CTkFrame(page)
        row.pack(fill="x", pady=4)
        ctk.CTkButton(row, text=_t("create"), command=self._gloss_create).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row, text=_t("build_from_pair"), command=self._gloss_build
        ).pack(side="left", padx=4)
        ctk.CTkButton(row, text=_t("refresh"), command=self._gloss_refresh).pack(
            side="left", padx=4
        )
        self.gloss_box = ctk.CTkTextbox(page, font=("Consolas", 13))
        self.gloss_box.pack(fill="both", expand=True, pady=8)
        self._gloss_refresh()

    def _gloss_create(self) -> None:
        name = simpledialog.askstring(
            _t("glossary"),
            _t("glossary_name_prompt"),
            initialvalue=_t("glossary_name_default"),
        )
        if not name:
            return
        g = self.glossary_store.create(name)
        self.gloss_box.insert("end", _t("glossary_created", id=g.glossary_id) + "\n")
        self._gloss_refresh()

    def _gloss_build(self) -> None:
        src = filedialog.askopenfilename(
            title=_t("original_book"),
            filetypes=[(_t("filetypes_ebook"), "*.epub *.txt")],
        )
        if not src:
            return
        tgt = filedialog.askopenfilename(
            title=_t("official_translation"),
            filetypes=[(_t("filetypes_ebook"), "*.epub *.txt")],
        )
        if not tgt:
            return
        name = (
            simpledialog.askstring(
                _t("glossary"),
                _t("glossary_build_name"),
                initialvalue="auto",
            )
            or "auto"
        )
        src_book = parse_to_book(src).book
        tgt_book = parse_to_book(tgt).book
        result = build_candidates_from_alignment(src_book, tgt_book)
        g = self.glossary_store.create(name, entries=result.candidates)
        msg = _t(
            "glossary_build_result",
            id=g.glossary_id[:8],
            candidates=len(result.candidates),
            pairs=len(result.pairs),
        )
        if result.needs_manual_alignment:
            msg += "\n" + _t("glossary_manual_align", message=result.message)
        self.gloss_box.insert("end", msg + "\n")
        self._gloss_refresh()

    def _gloss_refresh(self) -> None:
        self.gloss_box.delete("1.0", "end")
        for gid in self.glossary_store.list_ids():
            g = self.glossary_store.load(gid)
            confirmed = sum(1 for e in g.entries if e.confirmed)
            self.gloss_box.insert(
                "end",
                _t(
                    "glossary_row",
                    id=gid[:8],
                    name=g.name,
                    version=g.version,
                    entries=len(g.entries),
                    confirmed=confirmed,
                )
                + "\n",
            )

    # ================================================================ Settings
    def _open_settings(self) -> None:
        """Settings UI covering §42 sections."""
        ctk = _ctk()
        win = ctk.CTkToplevel(self.root)
        win.title(_t("settings"))
        win.geometry("560x640")

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        entries: dict[str, object] = {}

        def section(title_key: str) -> None:
            ctk.CTkLabel(
                scroll, text=_t(title_key), font=("", 14, "bold")
            ).pack(anchor="w", pady=(12, 4))

        def field(key: str, label_key: str, value: str) -> None:
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=_t(label_key), width=180, anchor="w").pack(
                side="left"
            )
            e = ctk.CTkEntry(row, width=280)
            e.insert(0, value)
            e.pack(side="left", padx=4)
            entries[key] = e

        section("settings_ai")
        field("endpoint", "label_endpoint", self.settings.ai.endpoint)
        field("model", "label_model", self.settings.ai.model)
        field(
            "model_identifier",
            "label_model_id",
            self.settings.ai.model_identifier or "",
        )
        field("api_key", "label_api_key", self.settings.ai.api_key)

        section("settings_translation")
        field(
            "source_language",
            "label_source_lang",
            self.settings.translation.source_language,
        )
        field(
            "target_language",
            "label_target_lang",
            self.settings.translation.target_language,
        )
        field("style", "label_style", self.settings.translation.style)
        field(
            "chunk_target_tokens",
            "label_chunk_tokens",
            str(self.settings.translation.chunk_target_tokens),
        )
        field(
            "carry_over_paragraphs",
            "label_carry_over",
            str(self.settings.translation.carry_over_paragraphs),
        )

        section("settings_retry")
        field(
            "timeout_seconds",
            "label_timeout",
            str(self.settings.ai.timeout_seconds),
        )
        field(
            "retry_count",
            "label_retry_count",
            str(self.settings.ai.retry_count),
        )
        field(
            "retry_delay_seconds",
            "label_retry_delay",
            str(self.settings.ai.retry_delay_seconds),
        )
        field(
            "request_interval_seconds",
            "label_request_interval",
            str(self.settings.ai.request_interval_seconds),
        )
        field(
            "endpoint_fail_threshold",
            "label_endpoint_fail",
            str(self.settings.ai.endpoint_fail_threshold),
        )

        section("settings_output")
        field(
            "after_completion",
            "label_after_completion",
            self.settings.output.after_completion,
        )
        ctk.CTkLabel(
            scroll, text=_t("hint_after_completion"), anchor="w"
        ).pack(anchor="w", padx=4)

        section("settings_interface")
        field(
            "interface_language",
            "label_interface_lang",
            self.settings.interface_language or "(auto)",
        )
        ctk.CTkLabel(
            scroll, text=_t("hint_interface_lang"), anchor="w"
        ).pack(anchor="w", padx=4)

        section("settings_advanced")
        field(
            "max_image_edge",
            "label_max_image_edge",
            str(self.settings.max_image_edge),
        )

        def _get(key: str) -> str:
            return entries[key].get().strip()  # type: ignore[union-attr]

        def _get_float(key: str, default: float) -> float:
            try:
                return float(_get(key))
            except ValueError:
                return default

        def _get_int(key: str, default: int) -> int:
            try:
                return int(float(_get(key)))
            except ValueError:
                return default

        def save() -> None:
            self.settings.ai.endpoint = _get("endpoint")
            self.settings.ai.model = _get("model")
            self.settings.ai.model_identifier = _get("model_identifier")
            self.settings.ai.api_key = _get("api_key") or "local"
            self.settings.ai.timeout_seconds = _get_float("timeout_seconds", 120.0)
            self.settings.ai.retry_count = _get_int("retry_count", 3)
            self.settings.ai.retry_delay_seconds = _get_float(
                "retry_delay_seconds", 2.0
            )
            self.settings.ai.request_interval_seconds = _get_float(
                "request_interval_seconds", 0.5
            )
            self.settings.ai.endpoint_fail_threshold = _get_int(
                "endpoint_fail_threshold", 3
            )
            self.settings.translation.source_language = _get("source_language")
            self.settings.translation.target_language = _get("target_language")
            self.settings.translation.style = _get("style")
            self.settings.translation.chunk_target_tokens = _get_int(
                "chunk_target_tokens", 1000
            )
            self.settings.translation.carry_over_paragraphs = _get_int(
                "carry_over_paragraphs", 2
            )
            self.settings.output.after_completion = _get("after_completion") or "nothing"
            lang = _get("interface_language")
            self.settings.interface_language = (
                "" if lang in ("", "(auto)") else lang
            )
            self.settings.max_image_edge = _get_int("max_image_edge", 1600)
            self.settings.save(self.settings_path)
            if self.settings.interface_language:
                i18n.set_language(self.settings.interface_language)
            win.destroy()

        ctk.CTkButton(win, text=_t("save"), command=save).pack(pady=12)

    def run(self) -> None:
        self.root.mainloop()


def launch() -> None:
    App().run()


if __name__ == "__main__":
    launch()
