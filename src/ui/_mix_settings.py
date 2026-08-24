"""Settings page mixin — finite dropdowns + restart UX."""
from __future__ import annotations

from tkinter import messagebox

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
        option_maps: dict[str, dict[str, str]] = {}  # key -> label→code

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
            initial = c2l.get(current, labels[0] if labels else "")
            menu = ctk.CTkOptionMenu(row, values=labels, width=280)
            menu.set(initial)
            menu.pack(side="left", padx=4)
            entries[key] = menu

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

        def _src_label(code: str) -> str:
            if code == "auto":
                return _t("src_auto")
            return code

        def _tgt_label(code: str) -> str:
            return code

        def _style_label(code: str) -> str:
            return {
                "fiction": _t("style_fiction"),
                "nonfiction": _t("style_nonfiction"),
            }.get(code, code)

        def _after_label(code: str) -> str:
            return {
                "nothing": _t("after_nothing"),
                "sleep": _t("after_sleep"),
                "shutdown": _t("after_shutdown"),
                "open_folder": _t("after_open_folder"),
            }.get(code, code)

        def _iface_label(code: str) -> str:
            return {
                "": _t("lang_auto"),
                "zh-HK": _t("lang_zh_hk"),
                "zh-TW": _t("lang_zh_tw"),
                "en": _t("lang_en"),
            }.get(code, code)

        dropdown(
            "source_language",
            "label_source_lang",
            _SOURCE_LANG_CODES,
            self.settings.translation.source_language,
            _src_label,
        )
        dropdown(
            "target_language",
            "label_target_lang",
            _TARGET_LANG_CODES,
            self.settings.translation.target_language,
            _tgt_label,
        )
        dropdown(
            "style",
            "label_style",
            _STYLE_CODES,
            self.settings.translation.style,
            _style_label,
        )
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
        ctk.CTkLabel(scroll, text=_t("label_prompt"), anchor="w").pack(
            anchor="w", pady=(8, 2)
        )
        prompt_box = ctk.CTkTextbox(scroll, height=100)
        prompt_box.pack(fill="x", pady=2)
        # Load style-specific saved prompt, else empty (default used at runtime)
        _st = (self.settings.translation.style or "fiction").lower()
        _saved = (
            self.settings.translation.fiction_prompt
            if _st.startswith("fiction")
            else self.settings.translation.nonfiction_prompt
        )
        _initial = self.settings.translation.prompt or _saved or ""
        if _initial:
            prompt_box.insert("1.0", _initial)
        entries["prompt"] = prompt_box
        ctk.CTkLabel(scroll, text=_t("hint_prompt"), anchor="w").pack(
            anchor="w", padx=4
        )

        def _reset_prompt() -> None:
            from src.translation.prompts import default_prompt_for_style
            style_code = "fiction"
            # resolve current style from dropdown if available
            try:
                lab = entries.get("style")
                if lab is not None:
                    cur = lab.get() if hasattr(lab, "get") else str(lab)
                    if _t("style_nonfiction") in str(cur) or "nonfiction" in str(cur).lower():
                        style_code = "nonfiction"
            except Exception:
                pass
            prompt_box.delete("1.0", "end")
            prompt_box.insert("1.0", default_prompt_for_style(style_code))

        ctk.CTkButton(
            scroll, text=_t("reset_to_default"), command=_reset_prompt, width=140
        ).pack(anchor="w", pady=4)

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
        dropdown(
            "after_completion",
            "label_after_completion",
            _AFTER_CODES,
            self.settings.output.after_completion,
            _after_label,
        )

        section("settings_interface")
        dropdown(
            "interface_language",
            "label_interface_lang",
            _INTERFACE_LANG_CODES,
            self.settings.interface_language or "",
            _iface_label,
        )

        section("settings_advanced")
        field(
            "max_image_edge",
            "label_max_image_edge",
            str(self.settings.max_image_edge),
        )

        def _get(key: str) -> str:
            w = entries[key]
            if key in option_maps:
                lab = w.get()  # type: ignore[union-attr]
                return option_maps[key].get(lab, lab)
            if hasattr(w, "get") and "Textbox" not in type(w).__name__:
                return w.get().strip()  # type: ignore[union-attr]
            return w.get("1.0", "end").strip()  # type: ignore[union-attr]

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
            prev_lang = self.settings.interface_language
            try:
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
                self.settings.translation.prompt = _get("prompt")
                _psave = self.settings.translation.prompt or ""
                _stsave = (self.settings.translation.style or "fiction").lower()
                if "non" in _stsave:
                    self.settings.translation.style = "nonfiction"
                    self.settings.translation.nonfiction_prompt = _psave
                else:
                    self.settings.translation.style = "fiction"
                    self.settings.translation.fiction_prompt = _psave
                self.settings.output.after_completion = (
                    _get("after_completion") or "nothing"
                )
                self.settings.interface_language = _get("interface_language") or ""
                self.settings.max_image_edge = _get_int("max_image_edge", 1600)
                self.settings.save(self.settings_path)
            except Exception as e:
                log.exception("settings save failed")
                self._show_error("error", str(e))
                return

            lang_changed = (
                (self.settings.interface_language or "") != (prev_lang or "")
            )
            win.destroy()
            if lang_changed:
                self._prompt_restart_for_language()
            else:
                messagebox.showinfo(
                    _t("info"), _t("settings_saved"), parent=self.root
                )

        ctk.CTkButton(win, text=_t("save"), command=save).pack(pady=12)

    def _prompt_restart_for_language(self) -> None:

        ctk = _ctk()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(_t("restart_required"))
        dlg.geometry("420x160")
        dlg.transient(self.root)
        dlg.grab_set()
        ctk.CTkLabel(
            dlg, text=_t("restart_prompt"), wraplength=380, justify="left"
        ).pack(padx=16, pady=16)

        def do_restart() -> None:
            dlg.destroy()
            try:
                # Settings already saved by caller
                _relaunch_process()
            except Exception as e:
                log.exception("relaunch failed")
                self._show_error("error", str(e))
                return
            self.root.destroy()

        def do_later() -> None:
            dlg.destroy()
            messagebox.showinfo(
                _t("info"), _t("settings_saved"), parent=self.root
            )

        row = ctk.CTkFrame(dlg)
        row.pack(pady=8)
        ctk.CTkButton(row, text=_t("restart_now"), command=do_restart).pack(
            side="left", padx=8
        )
        ctk.CTkButton(row, text=_t("restart_later"), command=do_later).pack(
            side="left", padx=8
        )
