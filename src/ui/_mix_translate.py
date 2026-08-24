"""Translate page mixin — BatchQueue lifecycle aligned (items/start/item_id)."""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from src.models.job import JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action
from src.ui.paths import ebook_filetypes
from src.ui._common import _ctk, _t, log


class TranslateMixin:

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

        gloss_row = ctk.CTkFrame(page)
        gloss_row.pack(fill="x", pady=4, padx=4)
        ctk.CTkLabel(gloss_row, text=_t("label_global_glossary")).pack(side="left", padx=4)
        self._global_gloss_var = ctk.StringVar(value=_t("glossary_none"))
        self._global_gloss_menu = ctk.CTkOptionMenu(
            gloss_row, variable=self._global_gloss_var, values=[_t("glossary_none")], width=180
        )
        self._global_gloss_menu.pack(side="left", padx=4)
        ctk.CTkLabel(gloss_row, text=_t("label_book_glossary")).pack(side="left", padx=8)
        self._book_gloss_var = ctk.StringVar(value=_t("glossary_none"))
        self._book_gloss_menu = ctk.CTkOptionMenu(
            gloss_row, variable=self._book_gloss_var, values=[_t("glossary_none")], width=180
        )
        self._book_gloss_menu.pack(side="left", padx=4)
        ctk.CTkButton(
            gloss_row, text=_t("refresh"), width=70, command=self._refresh_glossary_dropdowns
        ).pack(side="left", padx=4)

        # Queue item list with lifecycle actions
        mid = ctk.CTkFrame(page)
        mid.pack(fill="both", expand=False, pady=4)
        ctk.CTkLabel(mid, text=_t("queue_items"), font=("", 13, "bold")).pack(anchor="w")
        self.queue_list = ctk.CTkScrollableFrame(mid, height=160)
        self.queue_list.pack(fill="x", expand=False)

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
        try:
            self._refresh_glossary_dropdowns()
        except Exception:
            pass

        self.translate_log = ctk.CTkTextbox(page, font=("Consolas", 13), height=120)
        self.translate_log.pack(fill="both", expand=True, pady=8)

    def _refresh_queue_list(self) -> None:
        ctk = _ctk()
        for w in self.queue_list.winfo_children():
            w.destroy()
        if not self._queue:
            return
        for item in self._queue.items():
            row = ctk.CTkFrame(self.queue_list)
            row.pack(fill="x", pady=2)
            name = item.display_name or Path(item.source_path).name
            st = item.status.value if hasattr(item.status, "value") else str(item.status)
            ctk.CTkLabel(
                row, text=f"{name}  [{st}]", anchor="w", width=320
            ).pack(side="left", padx=4)
            # Status-specific actions
            if item.status == JobStatus.PENDING:
                ctk.CTkButton(
                    row, text=_t("remove"), width=70,
                    command=lambda iid=item.item_id: self._queue_remove(iid),
                ).pack(side="right", padx=2)
            elif item.status == JobStatus.PROCESSING:
                ctk.CTkButton(
                    row, text=_t("pause"), width=70,
                    command=lambda iid=item.item_id: self._queue_pause_job(iid),
                ).pack(side="right", padx=2)
                ctk.CTkButton(
                    row, text=_t("cancel"), width=70,
                    command=lambda iid=item.item_id: self._queue_cancel(iid),
                ).pack(side="right", padx=2)
            elif item.status == JobStatus.PAUSED:
                ctk.CTkButton(
                    row, text=_t("resume"), width=70,
                    command=lambda iid=item.item_id: self._queue_resume_job(iid),
                ).pack(side="right", padx=2)
                ctk.CTkButton(
                    row, text=_t("remove"), width=70,
                    command=lambda iid=item.item_id: self._queue_remove(iid),
                ).pack(side="right", padx=2)
            elif item.status == JobStatus.COMPLETED:
                ctk.CTkButton(
                    row, text=_t("remove"), width=70,
                    command=lambda iid=item.item_id: self._queue_remove(iid),
                ).pack(side="right", padx=2)
            elif item.status == JobStatus.COMPLETED_WITH_ERRORS:
                ctk.CTkButton(
                    row, text=_t("remove"), width=70,
                    command=lambda iid=item.item_id: self._queue_remove(iid),
                ).pack(side="right", padx=2)
            elif item.status == JobStatus.CANCELLED:
                ctk.CTkButton(
                    row, text=_t("remove"), width=70,
                    command=lambda iid=item.item_id: self._queue_remove(iid),
                ).pack(side="right", padx=2)

    def _queue_remove(self, item_id: str) -> None:
        if not self._queue:
            return
        delete = messagebox.askyesno(
            _t("confirm"),
            _t("remove_job_delete_data_q"),
            parent=self.root,
        )
        try:
            self._queue.remove(item_id, delete_job_data=bool(delete))
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._refresh_queue_list()

    def _queue_cancel(self, item_id: str) -> None:
        if not self._queue:
            return
        try:
            self._queue.cancel_job(item_id)
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._refresh_queue_list()

    def _queue_pause_job(self, item_id: str) -> None:
        if not self._queue:
            return
        try:
            self._queue.pause_job(item_id)
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._refresh_queue_list()

    def _queue_resume_job(self, item_id: str) -> None:
        if not self._queue:
            return
        try:
            self._queue.resume_job(item_id)
            if self._queue.status.value != "running":
                self._queue.resume()
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._refresh_queue_list()

    def _queue_progress(self, event, data):
        def ui():
            self._refresh_queue_list()
            if event == "chunk_done":
                total = max(int(data.get("total") or 1), 1)
                completed = int(data.get("completed") or 0)
                failed = int(data.get("failed") or 0)
                done = completed + failed
                pct = int(100 * done / total)
                self.progress_bar.set(done / total)
                self.lbl_chunk.configure(
                    text=_t("progress_chunk", current=done, total=total)
                )
                self.lbl_overall.configure(
                    text=_t("progress_overall", percent=pct)
                )
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

    def _add_translate(self) -> None:
        try:
            paths = filedialog.askopenfilenames(
                parent=self.root,
                filetypes=ebook_filetypes(
                    _t("filetypes_ebook"), _t("filetypes_epub"), _t("filetypes_all")
                ),
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not paths:
            return
        try:
            out = filedialog.askdirectory(parent=self.root, title=_t("output_folder"))
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not out:
            return
        self._translate_output_dir = Path(out)
        self._ensure_queue()
        assert self._queue is not None
        for p in paths:
            path = Path(p)
            self._queue.add(
                path,
                self._translate_output_dir / f"{path.stem}.translated.epub",
                display_name=path.name,
            )
        self._refresh_queue_list()
        self.translate_log.insert(
            "end", _t("queued_books", count=len(paths)) + "\n"
        )

    def _start_queue(self) -> None:
        self._ensure_queue()
        assert self._queue is not None
        if not self._queue.items():
            messagebox.showinfo(
                _t("info"), _t("add_books_output_first"), parent=self.root
            )
            return
        try:
            self._queue.glossary = self._selected_glossary_entries()
            try:
                mode = self._current_conversion_mode()
                self._queue.conversion_mode = mode
                self.settings.output.conversion_mode = mode
            except Exception:
                pass
            self._queue.start()
            self.translate_log.insert("end", _t("queue_started") + "\n")
            self._refresh_queue_list()
            threading.Thread(target=self._watch_queue, daemon=True).start()
        except Exception as e:
            log.exception("start queue failed")
            self._show_error("error", str(e))

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
            self.translate_log.insert("end", _t("pause_requested") + "\n")

    def _resume_queue(self) -> None:
        if self._queue:
            self._queue.resume()
            self.translate_log.insert("end", _t("resume_log") + "\n")
            threading.Thread(target=self._watch_queue, daemon=True).start()

    def _refresh_glossary_dropdowns(self) -> None:
        """Populate both selectors with the same list of all glossaries.

        Global Glossary / Book Glossary are two independent selection slots
        only — not different glossary types or scopes. Any glossary may be
        chosen in either slot (or None).
        """
        none_label = _t("glossary_none")
        labels = [none_label]
        self._gloss_label_to_id: dict[str, str] = {}
        try:
            store = getattr(self, "glossary_store", None) or getattr(
                self, "_glossary_store", None
            )
            if store is not None:
                for gid in store.list_ids():
                    try:
                        g = store.load(gid)
                    except Exception:
                        continue
                    label = f"{g.name} ({g.glossary_id[:8]})"
                    labels.append(label)
                    self._gloss_label_to_id[label] = g.glossary_id
        except Exception:
            log.exception("refresh glossary dropdowns")
        try:
            self._global_gloss_menu.configure(values=labels)
            self._book_gloss_menu.configure(values=labels)
            if self._global_gloss_var.get() not in labels:
                self._global_gloss_var.set(none_label)
            if self._book_gloss_var.get() not in labels:
                self._book_gloss_var.set(none_label)
        except Exception:
            pass

    def _selected_glossary_entries(self) -> list[dict[str, str]]:
        """Merge confirmed entries from the two independent selector slots.

        Same semantics for both slots — no Global/Book term behavior difference.
        Duplicate sources are deduplicated (first selector wins).
        """
        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        store = getattr(self, "glossary_store", None) or getattr(
            self, "_glossary_store", None
        )
        if store is None:
            return entries
        mapping = getattr(self, "_gloss_label_to_id", {}) or {}
        for var_name in ("_global_gloss_var", "_book_gloss_var"):
            try:
                label = getattr(self, var_name).get()
            except Exception:
                continue
            gid = mapping.get(label)
            if not gid:
                continue
            try:
                g = store.load(gid)
                for e in g.as_prompt_list(only_confirmed=True):
                    src = (e.get("source") or "").strip()
                    if not src or src in seen:
                        continue
                    seen.add(src)
                    entries.append(dict(e))
            except Exception:
                log.exception("load glossary %s for queue", gid)
        return entries
