"""UI mixin."""
from __future__ import annotations

from tkinter import messagebox

from src.core.settings import AppSettings
from src.ui._common import (
    _AFTER_CODES,
    _INTERFACE_LANG_CODES,
    _SOURCE_LANG_CODES,
    _STYLE_CODES,
    _TARGET_LANG_CODES,
    _ctk,
    _relaunch_process,
    _t,
    log,
)


class SettingsMixin:
    def _option_labels(
        self, codes: tuple[str, ...], label_for
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        labels = []
        l2c: dict[str, str] = {}
        c2l: dict[str, str] = {}
        for code in codes:
            lab = label_for(code)
            labels.append(lab)
            l2c[lab] = code
            c2l[code] = lab
        return labels, l2c, c2l

    def _open_settings(self) -> None:
        ctk = _ctk()
        win = ctk.CTkToplevel(self.root)
        win.title(_t("settings"))
        win.geometry("560x680")
        win.transient(self.root)

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        entries: dict[str, object] = {}
        option_maps: dict[str, dict[str, str]] = {}

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

        def dropdown(
            key: str,
            label_key: str,
            codes: tuple[str, ...],
            current: str,
            label_for,
        ) -> None:
            labels, l2c, c2l = self._option_labels(codes, label_for)
            option_maps[key] = l2c
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=_t(label_key), width=180, anchor="w").pack(
                side="left"
            )
            cur_label = c2l.get(current, labels[0] if labels else "")
            var = ctk.StringVar(value=cur_label)
            menu = ctk.CTkOptionMenu(row, variable=var, values=labels, width=280)
            menu.pack(side="left", padx=4)
            entries[key] = var

        def _iface_label(code: str) -> str:
            return {
                "": _t("lang_system"),
                "zh-HK": _t("lang_zh_hk"),
                "zh-TW": _t("lang_zh_tw"),
                "en": _t("lang_en"),
            }.get(code, code or _t("lang_system"))

        def _src_label(code: str) -> str:
            return {
                "auto": _t("lang_auto"),
                "en": "English",
                "ja": "Japanese",
                "zh": "Chinese",
                "zh-CN": "zh-CN",
                "zh-TW": "zh-TW",
                "ko": "Korean",
                "fr": "French",
                "de": "German",
                "es": "Spanish",
            }.get(code, code)

        def _tgt_label(code: str) -> str:
            return {
                "zh-TW": "zh-TW",
                "zh-HK": "zh-HK",
                "zh-CN": "zh-CN",
                "en": "English",
                "ja": "Japanese",
                "ko": "Korean",
            }.get(code, code)

        def _style_label(code: str) -> str:
            return _t(f"style_{code}") if code != "custom" else _t("style_custom")

        def _after_label(code: str) -> str:
            return _t(f"after_{code}")

        section("section_interface")
        dropdown(
            "interface_language",
            "interface_language",
            _INTERFACE_LANG_CODES,
            self.settings.interface_language or "",
            _iface_label,
        )

        section("section_translation")
        dropdown(
            "source_language",
            "source_language",
            _SOURCE_LANG_CODES,
            self.settings.translation.source_language,
            _src_label,
        )
        dropdown(
            "target_language",
            "target_language",
            _TARGET_LANG_CODES,
            self.settings.translation.target_language,
            _tgt_label,
        )
        dropdown(
            "style",
            "style",
            _STYLE_CODES,
            self.settings.translation.style,
            _style_label,
        )
        field(
            "prompt",
            "custom_prompt",
            self.settings.translation.prompt or "",
        )
        field(
            "chunk_target_tokens",
            "chunk_target_tokens",
            str(self.settings.translation.chunk_target_tokens),
        )
        field(
            "carry_over_paragraphs",
            "carry_over_paragraphs",
            str(self.settings.translation.carry_over_paragraphs),
        )

        section("section_ai")
        field("endpoint", "endpoint", self.settings.ai.endpoint)
        field("model", "model", self.settings.ai.model)
        field(
            "model_identifier",
            "model_identifier",
            self.settings.ai.model_identifier or "",
        )
        field("api_key", "api_key", self.settings.ai.api_key or "")
        field(
            "retry_count",
            "retry_count",
            str(self.settings.ai.retry_count),
        )
        field(
            "timeout_seconds",
            "timeout_seconds",
            str(self.settings.ai.timeout_seconds),
        )

        section("section_completion")
        dropdown(
            "after_completion",
            "after_completion",
            _AFTER_CODES,
            getattr(self.settings, "after_completion", "nothing") or "nothing",
            _after_label,
        )

        def _get(key: str) -> str:
            w = entries[key]
            if hasattr(w, "get"):
                return str(w.get()).strip()
            return ""

        def _get_int(key: str, default: int) -> int:
            try:
                return int(_get(key))
            except ValueError:
                return default

        def save() -> None:
            old_lang = self.settings.interface_language or ""
            iface = option_maps["interface_language"].get(
                _get("interface_language"), old_lang
            )
            src = option_maps["source_language"].get(
                _get("source_language"),
                self.settings.translation.source_language,
            )
            tgt = option_maps["target_language"].get(
                _get("target_language"),
                self.settings.translation.target_language,
            )
            style = option_maps["style"].get(
                _get("style"), self.settings.translation.style
            )
            after = option_maps["after_completion"].get(
                _get("after_completion"), "nothing"
            )

            self.settings.interface_language = iface
            self.settings.translation.source_language = src
            self.settings.translation.target_language = tgt
            self.settings.translation.style = style
            self.settings.translation.prompt = _get("prompt")
            self.settings.translation.chunk_target_tokens = _get_int(
                "chunk_target_tokens",
                self.settings.translation.chunk_target_tokens,
            )
            self.settings.translation.carry_over_paragraphs = _get_int(
                "carry_over_paragraphs",
                self.settings.translation.carry_over_paragraphs,
            )
            self.settings.ai.endpoint = _get("endpoint")
            self.settings.ai.model = _get("model")
            self.settings.ai.model_identifier = _get("model_identifier") or None
            self.settings.ai.api_key = _get("api_key") or None
            self.settings.ai.retry_count = _get_int(
                "retry_count", self.settings.ai.retry_count
            )
            self.settings.ai.timeout_seconds = _get_int(
                "timeout_seconds", self.settings.ai.timeout_seconds
            )
            try:
                self.settings.after_completion = after
            except Exception:
                pass

            try:
                self.settings.save(self.settings_path)
            except Exception as e:
                log.exception("save settings")
                messagebox.showerror(_t("error"), str(e), parent=win)
                return

            messagebox.showinfo(_t("done"), _t("settings_saved"), parent=win)
            if iface != old_lang:
                self._prompt_restart_for_language(win)
            else:
                win.destroy()

        def _prompt_restart_for_language(parent) -> None:
            dlg = ctk.CTkToplevel(parent)
            dlg.title(_t("restart_required"))
            dlg.geometry("360x140")
            dlg.transient(parent)
            ctk.CTkLabel(
                dlg, text=_t("restart_language_msg"), wraplength=320
            ).pack(padx=12, pady=12)

            def do_restart() -> None:
                dlg.destroy()
                parent.destroy()
                self.root.destroy()
                _relaunch_process()

            def do_later() -> None:
                dlg.destroy()
                parent.destroy()

            btn_row = ctk.CTkFrame(dlg)
            btn_row.pack(pady=8)
            ctk.CTkButton(
                btn_row, text=_t("restart_now"), command=do_restart
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                btn_row, text=_t("restart_later"), command=do_later
            ).pack(side="left", padx=8)

        btn_row = ctk.CTkFrame(win)
        btn_row.pack(fill="x", padx=8, pady=8)
        ctk.CTkButton(btn_row, text=_t("save"), command=save).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            btn_row, text=_t("cancel"), command=win.destroy
        ).pack(side="right", padx=4)
