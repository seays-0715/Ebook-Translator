"""Translate page mixin — BatchQueue lifecycle aligned (items/start/item_id)."""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import os
import subprocess
import sys

from src.core.languages import normalize_code
from src.models.job import JobStatus
from src.queue.batch_queue import BatchQueue
from src.translation.prompts import default_prompt_for_style
from src.utils.power import after_completion_action
from src.ui.paths import ebook_filetypes
from src.ui._common import (
    _STYLE_CODES,
    _ctk,
    _t,
    language_code_to_label,
    language_display_labels,
    language_label_to_code,
    log,
)


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

        cfg_row = ctk.CTkFrame(page)
        cfg_row.pack(fill="x", pady=4, padx=4)

        def _style_label(code: str) -> str:
            return {
                "fiction": _t("style_fiction"),
                "nonfiction": _t("style_nonfiction"),
            }.get(code, code)

        ts = self.settings.translation
        lang_labels = language_display_labels()
        style_codes = list(_STYLE_CODES)
        style_labels = [_style_label(c) for c in style_codes]
        self._tr_style_l2c = dict(zip(style_labels, style_codes))

        invalid_languages: list[str] = []
        try:
            src_code = normalize_code(ts.source_language)
        except ValueError as exc:
            src_code = (ts.source_language or "").strip()
            invalid_languages.append(f"source: {exc}")
        try:
            tgt_code = normalize_code(ts.target_language)
        except ValueError as exc:
            tgt_code = (ts.target_language or "").strip()
            invalid_languages.append(f"target: {exc}")

        ctk.CTkLabel(cfg_row, text=_t("label_source_lang")).pack(side="left", padx=4)
        self._tr_src_var = ctk.StringVar(value=language_code_to_label(src_code))
        ctk.CTkOptionMenu(
            cfg_row, variable=self._tr_src_var, values=lang_labels, width=160
        ).pack(side="left", padx=2)

        ctk.CTkLabel(cfg_row, text=_t("label_target_lang")).pack(side="left", padx=4)
        self._tr_tgt_var = ctk.StringVar(value=language_code_to_label(tgt_code))
        ctk.CTkOptionMenu(
            cfg_row, variable=self._tr_tgt_var, values=lang_labels, width=160
        ).pack(side="left", padx=2)

        if invalid_languages:
            self._translation_config_error = "; ".join(invalid_languages)
            ctk.CTkLabel(
                page,
                text=f"Invalid translation language configuration: {self._translation_config_error}",
                anchor="w",
                wraplength=900,
            ).pack(fill="x", padx=8, pady=(0, 4))
        else:
            self._translation_config_error = None

        ctk.CTkLabel(cfg_row, text=_t("label_style")).pack(side="left", padx=4)
        st = (ts.style or "fiction").lower()
        st_code = "nonfiction" if "non" in st else "fiction"
        self._tr_style_var = ctk.StringVar(value=_style_label(st_code))
        self._tr_style_menu = ctk.CTkOptionMenu(
            cfg_row,
            variable=self._tr_style_var,
            values=style_labels,
            width=120,
            command=self._on_style_changed,
        )
        self._tr_style_menu.pack(side="left", padx=2)

        prompt_hdr = ctk.CTkFrame(page)
        prompt_hdr.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(prompt_hdr, text=_t("label_prompt"), font=("", 12, "bold")).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            prompt_hdr,
            text=_t("reset_to_default"),
            width=120,
            command=self._reset_translate_prompt,
        ).pack(side="right", padx=4)
        self._tr_prompt_box = ctk.CTkTextbox(page, height=72, font=("", 12))
        self._tr_prompt_box.pack(fill="x", padx=4, pady=2)
        self._load_prompt_for_style(st_code)

        mid = ctk.CTkFrame(page)
        mid.pack(fill="both", expand=False, pady=4)
        ctk.CTkLabel(mid, text=_t("queue_items"), font=("", 13, "bold")).pack(anchor="w")
        self.queue_list = ctk.CTkScrollableFrame(mid, height=140)
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

        self.translate_log = ctk.CTkTextbox(page, font=("Consolas", 13), height=100)
        self.translate_log.pack(fill="both", expand=True, pady=8)

    def _prompt_for_style(self, style_code: str) -> str:
        """Saved custom for style, else built-in default template."""
        if style_code == "nonfiction":
            custom = getattr(self.settings.translation, "nonfiction_prompt", "") or ""
        else:
            custom = getattr(self.settings.translation, "fiction_prompt", "") or ""
        if custom.strip():
            return custom
        return default_prompt_for_style(style_code)

    def _load_prompt_for_style(self, style_code: str) -> None:
        box = getattr(self, "_tr_prompt_box", None)
        if box is None:
            return
        try:
            box.delete("1.0", "end")
            box.insert("1.0", self._prompt_for_style(style_code))
        except Exception:
            log.exception("load prompt for style")

    def _on_style_changed(self, _choice: str = "") -> None:
        """When Style changes, load that style's prompt template/custom."""
        try:
            _, _, style = self._translation_page_config()
        except Exception:
            style = "fiction"
        self._load_prompt_for_style(style)

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

    def _read_translate_prompt(self) -> str:
        box = getattr(self, "_tr_prompt_box", None)
        if box is None:
            return ""
        try:
            return box.get("1.0", "end").strip()
        except Exception:
            return ""

    def _persist_translate_prompt(self, style: str, text: str) -> None:
        """Save custom prompt per style (empty if matches built-in)."""
        builtin = default_prompt_for_style(style).strip()
        custom = "" if (text or "").strip() == builtin else (text or "").strip()
        if style == "nonfiction":
            self.settings.translation.nonfiction_prompt = custom
        else:
            self.settings.translation.fiction_prompt = custom

    def _refresh_queue_list(self) -> None:
        ctk = _ctk()
        for w in self.queue_list.winfo_children():
            w.destroy()
        if not self._queue:
            return
        for item in self._queue.items():
            frame = ctk.CTkFrame(self.queue_list)
            frame.pack(fill="x", pady=3)
            name = item.display_name or Path(item.source_path).name
            st = item.status.value if hasattr(item.status, "value") else str(item.status)

            top = ctk.CTkFrame(frame)
            top.pack(fill="x")
            ctk.CTkLabel(top, text=f"{name}  [{st}]", anchor="w", width=320).pack(side="left", padx=4)

            if item.status == JobStatus.PENDING:
                ctk.CTkButton(top, text=_t("remove"), width=70, command=lambda iid=item.item_id: self._queue_remove(iid)).pack(side="right", padx=2)
            elif item.status == JobStatus.PROCESSING:
                ctk.CTkButton(top, text=_t("pause"), width=70, command=lambda iid=item.item_id: self._queue_pause_job(iid)).pack(side="right", padx=2)
                ctk.CTkButton(top, text=_t("cancel"), width=70, command=lambda iid=item.item_id: self._queue_cancel(iid)).pack(side="right", padx=2)
            elif item.status == JobStatus.PAUSED:
                ctk.CTkButton(top, text=_t("resume"), width=70, command=lambda iid=item.item_id: self._queue_resume_job(iid)).pack(side="right", padx=2)
                ctk.CTkButton(top, text=_t("cancel"), width=70, command=lambda iid=item.item_id: self._queue_cancel(iid)).pack(side="right", padx=2)
            elif item.status == JobStatus.COMPLETED:
                out = (item.output_path or "").strip()
                if out:
                    ctk.CTkLabel(frame, text=_t("output_path_line", path=out), anchor="w").pack(fill="x", padx=8)
                ctk.CTkButton(top, text=_t("open_file_action"), width=80, command=lambda path=out: self._open_path(path, folder=False)).pack(side="right", padx=2)
                ctk.CTkButton(top, text=_t("open_folder_action"), width=90, command=lambda path=out: self._open_path(path, folder=True)).pack(side="right", padx=2)
                ctk.CTkButton(top, text=_t("remove"), width=70, command=lambda iid=item.item_id: self._queue_remove(iid)).pack(side="right", padx=2)
            elif item.status == JobStatus.COMPLETED_WITH_ERRORS:
                summary = self._readable_error_summary(item)
                if summary:
                    ctk.CTkLabel(frame, text=summary, anchor="w").pack(fill="x", padx=8)
                ctk.CTkButton(top, text=_t("retry"), width=70, command=lambda iid=item.item_id: self._queue_retry(iid)).pack(side="right", padx=2)
                ctk.CTkButton(top, text=_t("remove"), width=70, command=lambda iid=item.item_id: self._queue_remove(iid)).pack(side="right", padx=2)
            elif item.status == JobStatus.CANCELLED:
                ctk.CTkButton(top, text=_t("remove"), width=70, command=lambda iid=item.item_id: self._queue_remove(iid)).pack(side="right", padx=2)

    def _queue_remove(self, item_id: str) -> None:
        if not self._queue:
            return
        delete = messagebox.askyesno(_t("confirm"), _t("remove_job_delete_data_q"), parent=self.root)
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
                self.lbl_chunk.configure(text=_t("progress_chunk", current=done, total=total))
                self.lbl_overall.configure(text=_t("progress_overall", percent=pct))
            elif event == "item_exported":
                self.translate_log.insert("end", _t("progress_exported", path=data.get("output")) + "\n")
            elif event == "item_export_failed":
                self.translate_log.insert("end", _t("export_failed_msg") + "\n")
            elif event == "item_error":
                self.translate_log.insert("end", _t("translation_failed_msg") + "\n")
            elif event == "queue_finished":
                self.progress_label.configure(text=_t("queue_finished"))
                out_dir = self._translate_output_dir
                after_completion_action(self.settings.output.after_completion, output_folder=out_dir)
        self.root.after(0, ui)

    def _translation_page_config(self) -> tuple[str, str, str]:
        """Read Source / Target / Style from Translation page controls."""
        style = "fiction"
        src = language_label_to_code(self._tr_src_var.get())
        tgt = language_label_to_code(self._tr_tgt_var.get())
        try:
            style = self._tr_style_l2c.get(self._tr_style_var.get(), "fiction")
        except Exception:
            style = getattr(self.settings.translation, "style", None) or "fiction"
        style = "nonfiction" if "non" in str(style).lower() else "fiction"
        src = normalize_code(src)
        tgt = normalize_code(tgt)
        return src, tgt, style

    def _readable_error_summary(self, item) -> str:
        """Short human-readable summary; no stack traces."""
        err = (getattr(item, "error", None) or "") or ""
        if err.startswith("export_failed:") or err.startswith("Export failed"):
            return _t("export_failed_msg")
        try:
            if item.job_id and self.storage:
                job = self.storage.load_job(item.job_id)
                failed = int(getattr(job, "failed_chunks", 0) or 0)
                if failed > 0:
                    return _t("chapters_failed_summary", n=failed)
        except Exception:
            pass
        return _t("translation_failed_msg")

    def _open_path(self, path: str, *, folder: bool = False) -> None:
        if not path:
            return
        p = Path(path)
        target = str(p.parent if folder else p)
        if folder and not p.parent.exists():
            return
        if not folder and not p.exists():
            messagebox.showinfo(_t("info"), _t("output_missing"), parent=self.root)
            return
        try:
            if sys.platform == "win32":
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as e:
            self._show_error("error", str(e))

    def _queue_retry(self, item_id: str) -> None:
        if not self._queue:
            return
        try:
            self._queue.retry_job(item_id)
            if self._queue.status.value != "running":
                self._queue.start()
                threading.Thread(target=self._watch_queue, daemon=True).start()
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._refresh_queue_list()
        self.translate_log.insert("end", _t("retry_started") + "\n")

    def _add_translate(self) -> None:
        try:
            paths = filedialog.askopenfilenames(
                parent=self.root,
                filetypes=ebook_filetypes(_t("filetypes_ebook"), _t("filetypes_epub"), _t("filetypes_all")),
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not paths:
            return
        if hasattr(self, "_resolved_output_dir"):
            self._translate_output_dir = self._resolved_output_dir()
        else:
            from src.ui.paths import resolve_output_dir
            self._translate_output_dir = resolve_output_dir(getattr(self.settings.output, "default_dir", None))
        self._ensure_queue()
        assert self._queue is not None
        for p in paths:
            path = Path(p)
            self._queue.add(path, self._translate_output_dir / f"{path.stem}.translated.epub", display_name=path.name)
        self._refresh_queue_list()
        self.translate_log.insert("end", _t("queued_books", count=len(paths)) + "\n")

    def _start_queue(self) -> None:
        self._ensure_queue()
        assert self._queue is not None
        if not self._queue.items():
            messagebox.showinfo(_t("info"), _t("add_books_output_first"), parent=self.root)
            return
        try:
            try:
                src, tgt, style = self._translation_page_config()
            except ValueError as ve:
                self._show_error("error", str(ve))
                return
            try:
                self.settings.translation.source_language = src
                self.settings.translation.target_language = tgt
                self.settings.translation.style = style
                self._persist_translate_prompt(style, self._read_translate_prompt())
                from src.core.settings import save_settings
                save_settings(self.settings, self.settings_path)
            except Exception:
                log.exception("persist translation page defaults")
            if hasattr(self, "_job_config_from_settings"):
                self._queue.config = self._job_config_from_settings()
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
            self._queue.emit("queue_finished", {"status": self._queue.status.value})

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
        """Populate both selectors with the same list of all glossaries."""
        none_label = _t("glossary_none")
        labels = [none_label]
        self._gloss_label_to_id: dict[str, str] = {}
        try:
            store = getattr(self, "glossary_store", None) or getattr(self, "_glossary_store", None)
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
        """Merge confirmed entries from the two independent selector slots."""
        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        store = getattr(self, "glossary_store", None) or getattr(self, "_glossary_store", None)
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
