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
from src.core.languages import all_codes, code_to_name, display_pairs, normalize_code

log = logging.getLogger("ebook_translator.ui")

_INTERFACE_LANG_CODES = ("", "zh-HK", "zh-TW", "en")
# Source of truth: centralized registry (no Auto Detect)
_SOURCE_LANG_CODES = tuple(all_codes())
_TARGET_LANG_CODES = tuple(all_codes())
_STYLE_CODES = ("fiction", "nonfiction")
_CONVERSION_MODE_CODES = ("preserve", "clean", "simplified")
_AFTER_CODES = ("nothing", "sleep", "shutdown", "open_folder")


def _ctk():
    if ctk is None:
        raise RuntimeError(
            "customtkinter is not installed. Run: pip install customtkinter"
        )
    return ctk


def _t(key: str, **kwargs) -> str:
    return i18n.get(key, **kwargs)


def format_chapter_list_label(order: int, title: str | None) -> str:
    """Production chapter-list label: navigation index + title only.

    Must not include body text, block counts, character counts, or other
    content statistics. Body content belongs in the Chapter Preview pane.
    """
    t = (title or "").strip() or _t("untitled_chapter")
    return _t("chapter_row_compact", n=order + 1, title=t)


def language_display_labels() -> list[str]:
    """Human-readable names for OptionMenus (same order as registry)."""
    return [name for name, _ in display_pairs()]


def language_label_to_code(label: str) -> str:
    """Map UI display name (or code) back to stable code."""
    for name, code in display_pairs():
        if name == label or code == label:
            return code
    return normalize_code(label)


def language_code_to_label(code: str | None) -> str:
    """Map stable code to UI display name."""
    return code_to_name(code)


def _relaunch_process() -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        cwd = str(Path(sys.executable).resolve().parent)
    else:
        cmd = [sys.executable, "-m", "src.main", "--gui"]
        cwd = os.getcwd()
    log.info("Relaunching: %s (cwd=%s)", cmd, cwd)
    subprocess.Popen(cmd, cwd=cwd, close_fds=True)
