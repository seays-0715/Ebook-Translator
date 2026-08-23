"""UI mixin."""
from __future__ import annotations

import logging
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from src.glossary.builder import build_candidates_from_alignment
from src.ui._common import _ctk, _t, log


class GlossaryMixin:
    def _build_glossary_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["glossary"] = page

        top = ctk.CTkFrame(page)
        top.pack(fill="x", pady=4)
        for key, cmd in [
            ("create_glossary", self._gloss_create),
            ("import_glossary", self._gloss_import),
            ("export_glossary", self._gloss_export),
            ("build_from_job", self._gloss_build),
        ]:
            ctk.CTkButton(top, text=_t(key), command=cmd).pack(side="left", padx=4)

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)

        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(left, text=_t("glossaries"), font=("", 13, "bold")).pack(anchor="w")
        self.gloss_list = ctk.CTkScrollableFrame(left)
        self.gloss_list.pack(fill="both", expand=True)

        right = ctk.CTkFrame(body)
        right.pack(side="right", fill="both", expand=True, padx=(4, 0))
        ctk.CTkLabel(right, text=_t("entries"), font=("", 13, "bold")).pack(anchor="w")
        self.gloss_entries = ctk.CTkScrollableFrame(right)
        self.gloss_entries.pack(fill="both", expand=True)

        self.gloss_status = ctk.CTkLabel(page, text="", anchor="w")
        self.gloss_status.pack(fill="x", pady=4)
        self._gloss_refresh()

    def _gloss_create(self) -> None:
        name = simpledialog.askstring(
            _t("create_glossary"), _t("glossary_name_prompt"), parent=self.root
        )
        if not name:
            return
        try:
            g = self.glossary_store.create(name)
            self._selected_glossary_id = g.id
            self._gloss_refresh()
            self.gloss_status.configure(text=_t("glossary_created", name=name))
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_import(self) -> None:
        try:
            path = filedialog.askopenfilename(
                parent=self.root,
                title=_t("import_glossary"),
                filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("All", "*.*")],
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not path:
            return
        try:
            g = self.glossary_store.import_file(Path(path))
            self._selected_glossary_id = g.id
            self._gloss_refresh()
            self.gloss_status.configure(text=_t("glossary_imported", name=g.name))
        except Exception as e:
            log.exception("import glossary")
            self._show_error("error", str(e))

    def _gloss_export(self) -> None:
        if not self._selected_glossary_id:
            messagebox.showinfo(_t("info"), _t("select_glossary"), parent=self.root)
            return
        try:
            path = filedialog.asksaveasfilename(
                parent=self.root,
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
            )
        except Exception as e:
            self._show_error("error_open_file", str(e))
            return
        if not path:
            return
        try:
            self.glossary_store.export_file(self._selected_glossary_id, Path(path))
            self.gloss_status.configure(text=_t("glossary_exported", path=path))
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_build(self) -> None:
        if not self._selected_glossary_id:
            messagebox.showinfo(_t("info"), _t("select_glossary"), parent=self.root)
            return
        messagebox.showinfo(
            _t("info"),
            _t("build_from_job_hint"),
            parent=self.root,
        )

    def _gloss_select(self, gid: str) -> None:
        self._selected_glossary_id = gid
        self._gloss_refresh()

    def _gloss_confirm_entry(self, entry_id: str) -> None:
        if not self._selected_glossary_id:
            return
        try:
            self.glossary_store.confirm_entry(self._selected_glossary_id, entry_id)
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_reject_entry(self, entry_id: str) -> None:
        if not self._selected_glossary_id:
            return
        try:
            self.glossary_store.reject_entry(self._selected_glossary_id, entry_id)
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_edit_entry(self, entry_id: str) -> None:
        if not self._selected_glossary_id:
            return
        try:
            g = self.glossary_store.load(self._selected_glossary_id)
            entry = next((e for e in g.entries if e.id == entry_id), None)
            if not entry:
                return
            new_src = simpledialog.askstring(
                _t("edit_entry"), _t("source_term"), initialvalue=entry.source, parent=self.root
            )
            if new_src is None:
                return
            new_tgt = simpledialog.askstring(
                _t("edit_entry"), _t("target_term"), initialvalue=entry.target, parent=self.root
            )
            if new_tgt is None:
                return
            self.glossary_store.update_entry(
                self._selected_glossary_id, entry_id, source=new_src, target=new_tgt
            )
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_refresh(self) -> None:
        ctk = _ctk()
        try:
            for w in self.gloss_list.winfo_children():
                w.destroy()
            for w in self.gloss_entries.winfo_children():
                w.destroy()
            glossaries = self.glossary_store.list()
            for g in glossaries:
                selected = g.id == self._selected_glossary_id
                btn = ctk.CTkButton(
                    self.gloss_list,
                    text=f"{g.name} (v{g.version})",
                    anchor="w",
                    height=28,
                    fg_color=("gray75", "gray25") if selected else ("gray90", "gray20"),
                    text_color=("black", "white"),
                    command=lambda gid=g.id: self._gloss_select(gid),
                )
                btn.pack(fill="x", pady=1, padx=2)
            if self._selected_glossary_id:
                g = self.glossary_store.load(self._selected_glossary_id)
                for e in g.entries:
                    row = ctk.CTkFrame(self.gloss_entries)
                    row.pack(fill="x", pady=1)
                    status = getattr(e, "status", "pending")
                    lbl = ctk.CTkLabel(
                        row,
                        text=f"{e.source} → {e.target} [{status}]",
                        anchor="w",
                    )
                    lbl.pack(side="left", fill="x", expand=True, padx=4)
                    ctk.CTkButton(
                        row, text=_t("confirm"), width=60,
                        command=lambda eid=e.id: self._gloss_confirm_entry(eid),
                    ).pack(side="right", padx=1)
                    ctk.CTkButton(
                        row, text=_t("reject"), width=60,
                        command=lambda eid=e.id: self._gloss_reject_entry(eid),
                    ).pack(side="right", padx=1)
                    ctk.CTkButton(
                        row, text=_t("edit"), width=50,
                        command=lambda eid=e.id: self._gloss_edit_entry(eid),
                    ).pack(side="right", padx=1)
        except Exception as e:
            log.exception("glossary refresh failed")
            self._show_error("error", str(e))
