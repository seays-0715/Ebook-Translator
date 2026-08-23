"""Main application window — Convert / Translate / Glossary + Settings.

Convert page supports Chapter Preview ops: Merge / Split / Rename / Remove.
"""

from __future__ import annotations

import subprocess
import sys
import threading
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
from src.core.pipeline import convert_file, parse_to_book
from src.core.settings import AppSettings
from src.core.storage import Storage
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.glossary.store import GlossaryStore
from src.models.book import CanonicalBook
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action


def _ctk():
    if ctk is None:
        raise RuntimeError(
            "customtkinter is not installed. Run: pip install customtkinter"
        )
    return ctk


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
        self.root.title(i18n.get("app_title"))
        self.root.geometry("1024x680")

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
                text=i18n.get(label_key),
                command=lambda k=key: self._show(k),
            ).pack(fill="x", pady=4, padx=8)
        ctk.CTkButton(
            nav, text=i18n.get("settings"), command=self._open_settings
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
        ctk.CTkButton(top, text="Open File…", command=self._open_for_preview).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            top, text=i18n.get("confirm_convert"), command=self._do_convert
        ).pack(side="left", padx=4)

        # Book info
        self.info_label = ctk.CTkLabel(page, text="", anchor="w", justify="left")
        self.info_label.pack(fill="x", padx=4, pady=4)

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(left, text="Chapters").pack(anchor="w")
        self.chapter_list = ctk.CTkScrollableFrame(left)
        self.chapter_list.pack(fill="both", expand=True)
        self._chapter_buttons: list = []

        right = ctk.CTkFrame(body, width=200)
        right.pack(side="right", fill="y", padx=(4, 0))
        for text, cmd in [
            (i18n.get("merge"), self._op_merge),
            (i18n.get("split"), self._op_split),
            (i18n.get("rename"), self._op_rename),
            (i18n.get("remove"), self._op_remove),
        ]:
            ctk.CTkButton(right, text=text, command=cmd).pack(fill="x", pady=4, padx=8)

        self.convert_status = ctk.CTkLabel(page, text="", anchor="w")
        self.convert_status.pack(fill="x", pady=4)

    def _open_for_preview(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Ebook", "*.epub *.txt"), ("All", "*.*")]
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
            text=(
                f"Title: {meta.title}  |  Author: {meta.author}  |  "
                f"Lang: {meta.language}  |  Chapters: {len(result.book.chapters)}"
            )
        )
        if result.warnings:
            self.convert_status.configure(
                text="Warnings: " + "; ".join(result.warnings[:3])
            )
        else:
            self.convert_status.configure(text=f"Loaded {self._preview_source.name}")

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
            label = f"{ch.order + 1}. {ch.title}  ({len(ch.blocks)} blocks)"
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
            messagebox.showinfo("Info", "Open a file first")
            return None
        if not self._selected_chapter_id:
            messagebox.showinfo("Info", "Select a chapter")
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
            messagebox.showinfo("Info", "No next chapter to merge with")
            return
        try:
            self._preview_book = merge_adjacent(
                self._preview_book, cid, ids[idx + 1]
            )
            self._selected_chapter_id = cid
            self._refresh_chapter_list()
            self.convert_status.configure(text="Merged with next chapter")
        except ChapterOpError as e:
            messagebox.showerror("Error", str(e))

    def _op_split(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch or len(ch.blocks) < 2:
            messagebox.showinfo("Info", "Chapter needs at least 2 blocks to split")
            return
        # Split at midpoint (V1 simple UX; block picker can be richer later)
        mid = len(ch.blocks) // 2
        at_id = ch.blocks[mid].id
        try:
            self._preview_book = split_chapter(self._preview_book, cid, at_id)
            self._refresh_chapter_list()
            self.convert_status.configure(
                text=f"Split at block {at_id} (midpoint)"
            )
        except ChapterOpError as e:
            messagebox.showerror("Error", str(e))

    def _op_rename(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        ch = next((c for c in self._preview_book.chapters if c.id == cid), None)
        if not ch:
            return
        new_title = simpledialog.askstring(
            "Rename", "New chapter title:", initialvalue=ch.title
        )
        if not new_title:
            return
        try:
            self._preview_book = rename_chapter(
                self._preview_book, cid, new_title
            )
            self._refresh_chapter_list()
            self.convert_status.configure(text="Renamed")
        except ChapterOpError as e:
            messagebox.showerror("Error", str(e))

    def _op_remove(self) -> None:
        cid = self._require_book_and_selection()
        if not cid or not self._preview_book:
            return
        if not messagebox.askyesno("Confirm", "Remove this chapter?"):
            return
        try:
            self._preview_book = remove_chapter(self._preview_book, cid)
            self._selected_chapter_id = None
            self._refresh_chapter_list()
            self.convert_status.configure(text="Chapter removed")
        except ChapterOpError as e:
            messagebox.showerror("Error", str(e))

    def _do_convert(self) -> None:
        if not self._preview_book:
            messagebox.showinfo("Info", "Open and analyze a file first")
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".epub",
            filetypes=[("EPUB", "*.epub")],
            initialfile=(
                f"{self._preview_source.stem}.epub"
                if self._preview_source
                else "output.epub"
            ),
        )
        if not out:
            return
        generate_epub(self._preview_book, out)
        self.convert_status.configure(text=f"Wrote {out}")
        messagebox.showinfo("Done", f"Wrote\n{out}")

    # =============================================================== Translate
    def _build_translate_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["translate"] = page
        self._queue: BatchQueue | None = None
        self._translate_inputs: list[Path] = []
        self._translate_output_dir: Path | None = None

        row = ctk.CTkFrame(page)
        row.pack(fill="x", pady=4)
        ctk.CTkButton(row, text="Add Books…", command=self._add_translate).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row, text=i18n.get("start_translation"), command=self._start_queue
        ).pack(side="left", padx=4)
        ctk.CTkButton(row, text=i18n.get("pause"), command=self._pause_queue).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text=i18n.get("resume"), command=self._resume_queue).pack(
            side="left", padx=4
        )

        self.progress_label = ctk.CTkLabel(page, text="Idle", anchor="w")
        self.progress_label.pack(fill="x", padx=4)
        self.progress_bar = ctk.CTkProgressBar(page)
        self.progress_bar.pack(fill="x", padx=8, pady=4)
        self.progress_bar.set(0)

        self.translate_log = ctk.CTkTextbox(page, font=("Consolas", 13))
        self.translate_log.pack(fill="both", expand=True, pady=8)

    def _add_translate(self) -> None:
        paths = filedialog.askopenfilenames(
            filetypes=[("Ebook", "*.epub *.txt"), ("All", "*.*")]
        )
        self._translate_inputs = [Path(p) for p in paths]
        out = filedialog.askdirectory(title="Output folder")
        if out:
            self._translate_output_dir = Path(out)
        self.translate_log.insert(
            "end", f"Queued {len(self._translate_inputs)} book(s)\n"
        )

    def _start_queue(self) -> None:
        if not self._translate_inputs or not self._translate_output_dir:
            messagebox.showinfo("Info", "Add books and output folder first")
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
            retry_count=self.settings.ai.retry_count,
            request_timeout_seconds=self.settings.ai.timeout_seconds,
        )

        def on_progress(event, data):
            def ui():
                if event == "chunk_done":
                    total = max(int(data.get("total") or 1), 1)
                    done = int(data.get("completed") or 0) + int(
                        data.get("failed") or 0
                    )
                    self.progress_bar.set(done / total)
                    self.progress_label.configure(
                        text=(
                            f"Job {str(data.get('job_id', ''))[:8]}  "
                            f"{data.get('completed')}/{data.get('total')}  "
                            f"status={data.get('status')}"
                        )
                    )
                    self.translate_log.insert(
                        "end",
                        f"[{data.get('completed')}/{data.get('total')}] "
                        f"{data.get('status')}\n",
                    )
                    self.translate_log.see("end")
                elif event == "item_exported":
                    self.translate_log.insert(
                        "end", f"Exported {data.get('output')}\n"
                    )
                elif event == "queue_finished":
                    self.progress_label.configure(text="Queue finished")
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
        q.start()
        self.translate_log.insert("end", "Queue started\n")
        # Watch for completion in background
        threading.Thread(target=self._watch_queue, daemon=True).start()

    def _watch_queue(self) -> None:
        import time

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
            self.translate_log.insert("end", "Pause requested\n")

    def _resume_queue(self) -> None:
        if self._queue:
            self._queue.resume()
            self.translate_log.insert("end", "Resume\n")
            threading.Thread(target=self._watch_queue, daemon=True).start()

    # ================================================================ Glossary
    def _build_glossary_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["glossary"] = page
        row = ctk.CTkFrame(page)
        row.pack(fill="x", pady=4)
        ctk.CTkButton(row, text="Create", command=self._gloss_create).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row, text="Build from pair…", command=self._gloss_build
        ).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Refresh", command=self._gloss_refresh).pack(
            side="left", padx=4
        )
        self.gloss_box = ctk.CTkTextbox(page, font=("Consolas", 13))
        self.gloss_box.pack(fill="both", expand=True, pady=8)
        self._gloss_refresh()

    def _gloss_create(self) -> None:
        name = simpledialog.askstring("Glossary", "Name:", initialvalue="New Glossary")
        if not name:
            return
        g = self.glossary_store.create(name)
        self.gloss_box.insert("end", f"Created {g.glossary_id}\n")
        self._gloss_refresh()

    def _gloss_build(self) -> None:
        src = filedialog.askopenfilename(
            title="Original book",
            filetypes=[("Ebook", "*.epub *.txt")],
        )
        if not src:
            return
        tgt = filedialog.askopenfilename(
            title="Official translation",
            filetypes=[("Ebook", "*.epub *.txt")],
        )
        if not tgt:
            return
        name = simpledialog.askstring(
            "Glossary", "Glossary name:", initialvalue="auto"
        ) or "auto"
        src_book = parse_to_book(src).book
        tgt_book = parse_to_book(tgt).book
        result = build_candidates_from_alignment(src_book, tgt_book)
        g = self.glossary_store.create(name, entries=result.candidates)
        msg = (
            f"Glossary {g.glossary_id[:8]}  candidates={len(result.candidates)}  "
            f"pairs={len(result.pairs)}"
        )
        if result.needs_manual_alignment:
            msg += f"\nMANUAL ALIGNMENT: {result.message}"
        self.gloss_box.insert("end", msg + "\n")
        self._gloss_refresh()

    def _gloss_refresh(self) -> None:
        self.gloss_box.delete("1.0", "end")
        for gid in self.glossary_store.list_ids():
            g = self.glossary_store.load(gid)
            confirmed = sum(1 for e in g.entries if e.confirmed)
            self.gloss_box.insert(
                "end",
                f"{gid[:8]}  {g.name}  v{g.version}  "
                f"entries={len(g.entries)} confirmed={confirmed}\n",
            )

    # ================================================================ Settings
    def _open_settings(self) -> None:
        ctk = _ctk()
        win = ctk.CTkToplevel(self.root)
        win.title(i18n.get("settings"))
        win.geometry("520x420")
        fields = {
            "endpoint": self.settings.ai.endpoint,
            "model": self.settings.ai.model,
            "target_language": self.settings.translation.target_language,
            "style": self.settings.translation.style,
            "interface_language": self.settings.interface_language or "(auto)",
            "after_completion": self.settings.output.after_completion,
        }
        entries = {}
        for i, (k, v) in enumerate(fields.items()):
            ctk.CTkLabel(win, text=k).grid(row=i, column=0, padx=8, pady=4, sticky="w")
            e = ctk.CTkEntry(win, width=320)
            e.insert(0, v)
            e.grid(row=i, column=1, padx=8, pady=4)
            entries[k] = e
        hint = ctk.CTkLabel(
            win,
            text="after_completion: nothing | sleep | shutdown | open_folder",
            anchor="w",
        )
        hint.grid(row=len(fields), column=0, columnspan=2, padx=8, sticky="w")

        def save():
            self.settings.ai.endpoint = entries["endpoint"].get()
            self.settings.ai.model = entries["model"].get()
            self.settings.translation.target_language = entries[
                "target_language"
            ].get()
            self.settings.translation.style = entries["style"].get()
            lang = entries["interface_language"].get()
            self.settings.interface_language = "" if lang == "(auto)" else lang
            self.settings.output.after_completion = entries["after_completion"].get()
            self.settings.save(self.settings_path)
            if self.settings.interface_language:
                i18n.set_language(self.settings.interface_language)
            win.destroy()

        ctk.CTkButton(win, text="Save", command=save).grid(
            row=len(fields) + 1, column=0, columnspan=2, pady=12
        )

    def run(self) -> None:
        self.root.mainloop()


def launch() -> None:
    App().run()


if __name__ == "__main__":
    launch()
