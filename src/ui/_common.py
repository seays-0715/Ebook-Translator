"""Shared UI helpers and constants."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore

from src import i18n
from src.core.languages import all_display_names, display_pairs, name_to_code

log = logging.getLogger("ebook_translator.ui")

# UI interface language: exactly two options (no System default).
_INTERFACE_LANG_CODES = ("en", "zh-Hant")
_STYLE_CODES = ("fiction", "nonfiction")
_CONVERSION_MODE_CODES = ("standard", "compact")
_AFTER_CODES = ("nothing", "sleep", "shutdown", "open_folder")


def _ctk():
    if ctk is None:
        raise RuntimeError(
            "customtkinter is not installed. Run: pip install customtkinter"
        )
    return ctk


def _t(key: str, **kwargs) -> str:
    return i18n.get(key, **kwargs)


def language_display_labels() -> list[str]:
    """English display names for translation language OptionMenus."""
    return all_display_names()


def language_code_to_label(code: str) -> str:
    """Map registry code to English display name; falls back to code."""
    for name, c in display_pairs():
        if c == code:
            return name
    return code


def language_label_to_code(label: str) -> str:
    """Map English display name (or code) to registry code.

    Raises ValueError if the label is not a known language.
    """
    code = name_to_code(label)
    if code is None:
        raise ValueError(f"Unsupported language code: {label!r}")
    return code


def format_chapter_list_label(order: int, title: str | None) -> str:
    """Production chapter-list label: navigation index + title only.

    Must not include body text, block counts, character counts, or other
    content statistics. Body content belongs in the Chapter Preview pane.
    """
    t = (title or "").strip() or _t("untitled_chapter")
    return _t("chapter_row_compact", n=order + 1, title=t)


def _relaunch_process() -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        cwd = str(Path(sys.executable).resolve().parent)
    else:
        cmd = [sys.executable, "-m", "src.main", "--gui"]
        cwd = os.getcwd()
    log.info("Relaunching: %s (cwd=%s)", cmd, cwd)
    subprocess.Popen(cmd, cwd=cwd, close_fds=True)
