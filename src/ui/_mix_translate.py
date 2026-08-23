"""UI mixin."""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from src.models.job import JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action
from src.ui.paths import data_dir
from src.ui._common import _ctk, _t, log


class TranslateMixin:
    def _build_translate_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["translate"] = page

        top = ctk.CTkFrame(page)
        top.pack(fill="x", pady=4)
        ctk.CTkButton(top, text=_t("add_files"), command=self._add_translate_files).pack(
            side="left", padx=4
        )
        ctk.CTkButton(top, text=_t("set_output"), command=self._set_output_dir).pack(
            side="left", padx=4
        )
        ctk.CTkButton(top, text=_t("start_queue"), command=self._start_queue).pack(
            side="left", padx=4
        )
        ctk.CTkButton(top, text=_t("pause"), command=self._pause_queue).pack(
            side="left", padx=4
        )
        ctk.CTkButton(top, text=_t("resume"), command=self._resume_queue).pack(
            side="left", padx=4
        )

        mid = ctk.CTkFrame(page)
        mid.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(mid)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(left, text=_t("queue"), font=("", 13, "bold")).pack(anchor="w")
        self.queue_list = ctk.CTkScrollableFrame(left)
        self.queue_list.pack(fill="both", expand=True)
        self._queue_row_frames: dict[str, object] = {}

        right = ctk.CTkFrame(mid, width=220)
        right.pack(side="right", fill="y", padx=(4, 0))
        for key, cmd in [
            ("cancel_job", self._cancel_selected_job),
            ("remove_job", self._remove_selected_job),
            ("clear_completed", self._clear_completed),
        ]:
            ctk.CTkButton(right, text=_t(key), command=cmd).pack(
                fill="x", pady=4, padx=8
            )

        self.progress = ctk.CTkProgressBar(page)
        self.progress.pack(fill="x", padx=4, pady=4)
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(page, text="", anchor="w")
        self.progress_label.pack(fill="x", padx=4)

        self.translate_log = ctk.CTkTextbox(page, height=120)
        self.translate_log.pack(fill="x", padx=4, pady=4)

        self._selected_job_id: str | None = None

    def _add_translate_files(self) -> None:
        try:
            paths = filedialog.askopenfilenames(
                parent=self.root,
                title=_t("add_files"),
                filetypes=[
                    (_t("filetypes_ebook"), "*.epub;*.txt")
                    if sys.platform == "win32"
                    else (_t("filetypes_ebook"), "*.epub *.txt"),
                    (_t("filetypes_epub"), "*.epub"),
                    ("TXT", "*.txt"),
                ],
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not paths:
            return
        self._translate_inputs = [Path(p) for p in paths]
        if not self._translate_output_dir:
            self._set_output_dir()
        if not self._translate_output_dir:
            return
        self._ensure_queue()
        assert self._queue is not None
        for src in self._translate_inputs:
            out = self._translate_output_dir / f"{src.stem}.translated.epub"
            self._queue.add(src, out, display_name=src.name)
            self.translate_log.insert("end", _t("queued_file", name=src.name) + "\n")
        self._refresh_queue_list()

    def _set_output_dir(self) -> None:
        try:
            d = filedialog.askdirectory(parent=self.root, title=_t("output_folder"))
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if d:
            self._translate_output_dir = Path(d)
            self.translate_log.insert(
                "end", _t("output_set", path=str(self._translate_output_dir)) + "\n"
            )

    def _refresh_queue_list(self) -> None:
        ctk = _ctk()
        for w in self.queue_list.winfo_children():
            w.destroy()
        self._queue_row_frames.clear()
        if not self._queue:
            return
        for item in self._queue.items:
            row = ctk.CTkFrame(self.queue_list)
            row.pack(fill="x", pady=2, padx=2)
            status = item.status.value if hasattr(item.status, "value") else str(item.status)
            label = f"{item.display_name or item.source.name} [{status}]"
            selected = item.job_id == self._selected_job_id
            btn = ctk.CTkButton(
                row,
                text=label,
                anchor="w",
                height=28,
                fg_color=("gray75", "gray25") if selected else ("gray90", "gray20"),
                text_color=("black", "white"),
                command=lambda jid=item.job_id: self._select_job(jid),
            )
            btn.pack(fill="x", side="left", expand=True)
            self._queue_row_frames[item.job_id] = row

    def _select_job(self, job_id: str) -> None:
        self._selected_job_id = job_id
        self._refresh_queue_list()

    def _start_queue(self) -> None:
        self._ensure_queue()
        assert self._queue is not None
        if not self._queue.items:
            messagebox.showinfo(_t("info"), _t("queue_empty"), parent=self.root)
            return
        self.translate_log.insert("end", _t("queue_started") + "\n")
        threading.Thread(target=self._run_queue, daemon=True).start()

    def _run_queue(self) -> None:
        assert self._queue is not None
        try:
            self._queue.run()
        except Exception as e:
            log.exception("queue run failed")
            self.root.after(
                0, lambda: self._show_error("error", str(e))
            )
        finally:
            self.root.after(0, self._on_queue_finished)

    def _watch_queue(self) -> None:
        assert self._queue is not None
        try:
            self._queue.run()
        except Exception as e:
            log.exception("queue watch failed")
            self.root.after(0, lambda: self._show_error("error", str(e)))

    def _on_queue_finished(self) -> None:
        self._refresh_queue_list()
        self.progress.set(1.0)
        self.progress_label.configure(text=_t("queue_done"))
        self.translate_log.insert("end", _t("queue_done") + "\n")
        action = getattr(self.settings, "after_completion", None) or "nothing"
        if action and action != "nothing":
            try:
                after_completion_action(action)
            except Exception:
                log.exception("after_completion")

    def _queue_progress(self, job_id: str, done: int, total: int, message: str = "") -> None:
        def _ui():
            frac = (done / total) if total else 0.0
            self.progress.set(frac)
            self.progress_label.configure(
                text=_t("progress_fmt", done=done, total=total, msg=message or "")
            )
            self._refresh_queue_list()
        self.root.after(0, _ui)

    def _pause_queue(self) -> None:
        if self._queue:
            self._queue.pause()
            self.translate_log.insert("end", _t("pause_log") + "\n")

    def _resume_queue(self) -> None:
        if self._queue:
            self._queue.resume()
            self.translate_log.insert("end", _t("resume_log") + "\n")
            threading.Thread(target=self._watch_queue, daemon=True).start()

    def _cancel_selected_job(self) -> None:
        if not self._queue or not self._selected_job_id:
            return
        try:
            self._queue.cancel_job(self._selected_job_id)
            self.translate_log.insert(
                "end", _t("cancelled_job", id=self._selected_job_id) + "\n"
            )
            self._refresh_queue_list()
        except Exception as e:
            self._show_error("error", str(e))

    def _remove_selected_job(self) -> None:
        if not self._queue or not self._selected_job_id:
            return
        try:
            self._queue.remove(self._selected_job_id, delete_job_data=True)
            self.translate_log.insert(
                "end", _t("removed_job", id=self._selected_job_id) + "\n"
            )
            self._selected_job_id = None
            self._refresh_queue_list()
        except Exception as e:
            self._show_error("error", str(e))

    def _clear_completed(self) -> None:
        if not self._queue:
            return
        try:
            removed = self._queue.clear_completed()
            self.translate_log.insert(
                "end", _t("cleared_completed", n=removed) + "\n"
            )
            self._refresh_queue_list()
        except Exception as e:
            self._show_error("error", str(e))
