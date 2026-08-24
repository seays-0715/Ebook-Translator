"""Glossary page mixin — aligned with GlossaryStore API."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from src.core.pipeline import parse_to_book
from src.glossary.builder import build_candidates_from_alignment
from src.ui.paths import ebook_filetypes
from src.ui._common import _ctk, _t, log


class GlossaryMixin:
    def _build_glossary_page(self) -> None:
        ctk = _ctk()
        page = ctk.CTkFrame(self.content)
        self._pages["glossary"] = page
        self._selected_glossary_id: str | None = None
        self._gloss_entry_ids: list[str] = []

        row = ctk.CTkFrame(page)
        row.pack(fill="x", pady=4)
        for text_key, cmd in [
            ("create", self._gloss_create),
            ("build_from_pair", self._gloss_build),
            ("import", self._gloss_import),
            ("export", self._gloss_export),
            ("delete_glossary", self._gloss_delete),
            ("refresh", self._gloss_refresh),
        ]:
            ctk.CTkButton(row, text=_t(text_key), command=cmd).pack(
                side="left", padx=4
            )

        body = ctk.CTkFrame(page)
        body.pack(fill="both", expand=True, pady=4)
        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="y", padx=(0, 4))
        ctk.CTkLabel(left, text=_t("glossary_list")).pack(anchor="w")
        self.gloss_list = ctk.CTkScrollableFrame(left, width=220)
        self.gloss_list.pack(fill="y", expand=True)

        right = ctk.CTkFrame(body)
        right.pack(side="right", fill="both", expand=True)
        ctk.CTkLabel(right, text=_t("glossary_candidates")).pack(anchor="w")
        self.gloss_entries = ctk.CTkScrollableFrame(right)
        self.gloss_entries.pack(fill="both", expand=True)
        self._gloss_refresh()

    def _gloss_create(self) -> None:
        name = simpledialog.askstring(
            _t("glossary_name_prompt"),
            _t("glossary_name_prompt"),
            initialvalue=_t("glossary_name_default"),
            parent=self.root,
        )
        if not name:
            return
        try:
            g = self.glossary_store.create(name)
            self._selected_glossary_id = g.glossary_id
            messagebox.showinfo(
                _t("info"),
                _t("glossary_created", id=g.glossary_id[:8]),
                parent=self.root,
            )
            self._gloss_refresh()
        except Exception as e:
            log.exception("glossary create failed")
            self._show_error("error", str(e))

    def _gloss_import(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title=_t("import"),
            filetypes=[("JSON", "*.json"), (_t("filetypes_all"), "*.*")],
        )
        if not path:
            return
        try:
            g = self.glossary_store.import_json(path)
            self._selected_glossary_id = g.glossary_id
            self._gloss_refresh()
            messagebox.showinfo(
                _t("info"),
                _t("glossary_created", id=g.glossary_id[:8]),
                parent=self.root,
            )
        except Exception as e:
            log.exception("glossary import failed")
            self._show_error("error", str(e))

    def _gloss_export(self) -> None:
        if not self._selected_glossary_id:
            messagebox.showinfo(_t("info"), _t("select_glossary_first"), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"{self._selected_glossary_id[:8]}.json",
        )
        if not path:
            return
        try:
            self.glossary_store.export_json(self._selected_glossary_id, path)
            messagebox.showinfo(_t("done"), _t("wrote_file", path=path), parent=self.root)
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_build(self) -> None:
        try:
            src = filedialog.askopenfilename(
                parent=self.root,
                title=_t("original_book"),
                filetypes=ebook_filetypes(
                    _t("filetypes_ebook"), _t("filetypes_epub"), _t("filetypes_all")
                ),
            )
            if not src:
                return
            tgt = filedialog.askopenfilename(
                parent=self.root,
                title=_t("official_translation"),
                filetypes=ebook_filetypes(
                    _t("filetypes_ebook"), _t("filetypes_epub"), _t("filetypes_all")
                ),
            )
            if not tgt:
                return
            name = simpledialog.askstring(
                _t("glossary_build_name"),
                _t("glossary_build_name"),
                parent=self.root,
            )
            if not name:
                return
            src_book = parse_to_book(src).book
            tgt_book = parse_to_book(tgt).book
            result = build_candidates_from_alignment(src_book, tgt_book)
            g = self.glossary_store.create(name, entries=result.candidates)
            self._selected_glossary_id = g.glossary_id
            msg = _t(
                "glossary_build_result",
                id=g.glossary_id[:8],
                candidates=len(result.candidates),
                pairs=len(result.pairs),
            )
            if result.needs_manual_alignment:
                msg += "\n" + _t(
                    "glossary_manual_align", message=result.message or ""
                )
            messagebox.showinfo(_t("info"), msg, parent=self.root)
            self._gloss_refresh()
        except Exception as e:
            log.exception("glossary build failed")
            self._show_error("error", str(e))

    def _gloss_select(self, gid: str) -> None:
        self._selected_glossary_id = gid
        self._gloss_refresh()

    def _gloss_confirm_entry(self, eid: str) -> None:
        if not self._selected_glossary_id:
            return
        try:
            self.glossary_store.confirm_entry(self._selected_glossary_id, eid, True)
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_reject_entry(self, eid: str) -> None:
        if not self._selected_glossary_id:
            return
        try:
            self.glossary_store.reject_entry(self._selected_glossary_id, eid)
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_edit_entry(self, eid: str) -> None:
        if not self._selected_glossary_id:
            return
        g = self.glossary_store.load(self._selected_glossary_id)
        entry = next((e for e in g.entries if e.id == eid), None)
        if not entry:
            return
        src = simpledialog.askstring(
            _t("edit"), _t("label_source_lang"), initialvalue=entry.source, parent=self.root
        )
        if src is None:
            return
        tgt = simpledialog.askstring(
            _t("edit"), _t("label_target_lang"), initialvalue=entry.target, parent=self.root
        )
        if tgt is None:
            return
        try:
            self.glossary_store.update_entry(
                self._selected_glossary_id, eid, source=src, target=tgt
            )
            self._gloss_refresh()
        except Exception as e:
            self._show_error("error", str(e))

    def _gloss_refresh(self) -> None:
        ctk = _ctk()
        for w in self.gloss_list.winfo_children():
            w.destroy()
        for w in self.gloss_entries.winfo_children():
            w.destroy()
        try:
            for gid in self.glossary_store.list_ids():
                g = self.glossary_store.load(gid)
                confirmed = sum(1 for e in g.entries if e.confirmed)
                label = f"{g.name}  v{g.version}  ({confirmed}/{len(g.entries)})"
                selected = gid == self._selected_glossary_id
                ctk.CTkButton(
                    self.gloss_list,
                    text=label,
                    anchor="w",
                    fg_color=("gray75", "gray25") if selected else ("gray90", "gray20"),
                    text_color=("black", "white"),
                    command=lambda i=gid: self._gloss_select(i),
                ).pack(fill="x", pady=1)
            if self._selected_glossary_id:
                g = self.glossary_store.load(self._selected_glossary_id)
                for e in g.entries:
                    row = ctk.CTkFrame(self.gloss_entries)
                    row.pack(fill="x", pady=1)
                    mark = "\u2713" if e.confirmed else "\u00b7"
                    ctk.CTkLabel(
                        row,
                        text=f"{mark} {e.source} \u2192 {e.target}",
                        anchor="w",
                        width=280,
                    ).pack(side="left", padx=4)
                    if not e.confirmed:
                        ctk.CTkButton(
                            row, text=_t("confirm"), width=60,
                            command=lambda i=e.id: self._gloss_confirm_entry(i),
                        ).pack(side="right", padx=1)
                        ctk.CTkButton(
                            row, text=_t("reject"), width=60,
                            command=lambda i=e.id: self._gloss_reject_entry(i),
                        ).pack(side="right", padx=1)
                    ctk.CTkButton(
                        row, text=_t("edit"), width=50,
                        command=lambda i=e.id: self._gloss_edit_entry(i),
                    ).pack(side="right", padx=1)
        except Exception as e:
            log.exception("glossary refresh failed")
            self._show_error("error", str(e))

    def _gloss_delete(self) -> None:
        gid = getattr(self, "_selected_glossary_id", None)
        if not gid:
            messagebox.showinfo(_t("info"), _t("select_glossary_first"), parent=self.root)
            return
        if not messagebox.askyesno(_t("confirm"), _t("delete_glossary"), parent=self.root):
            return
        try:
            self.glossary_store.delete(gid)
        except Exception as e:
            self._show_error("error", str(e))
            return
        self._selected_glossary_id = None
        self._gloss_refresh()
