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

log = logging.getLogger("ebook_translator.ui")

_INTERFACE_LANG_CODES = ("", "zh-HK", "zh-TW", "en")
_SOURCE_LANG_CODES = ("auto", "en", "ja", "zh", "zh-CN", "zh-TW", "ko", "fr", "de", "es")
_TARGET_LANG_CODES = ("zh-TW", "zh-HK", "zh-CN", "en", "ja", "ko")
_STYLE_CODES = ("auto", "natural", "faithful", "literary", "light_novel", "custom")
_AFTER_CODES = ("nothing", "sleep", "shutdown", "open_folder")


def _ctk():
    if ctk is None:
        raise RuntimeError(
            "customtkinter is not installed. Run: pip install customtkinter"
        )
    return ctk


def _t(key: str, **kwargs) -> str:
    return i18n.get(key, **kwargs)


def _relaunch_process() -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        cwd = str(Path(sys.executable).resolve().parent)
    else:
        cmd = [sys.executable, "-m", "src.main", "--gui"]
        cwd = os.getcwd()
    log.info("Relaunching: %s (cwd=%s)", cmd, cwd)
    subprocess.Popen(cmd, cwd=cwd, close_fds=True)
