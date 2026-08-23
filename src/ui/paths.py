"""User-data paths and file-dialog helpers (no GUI imports)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4


def data_dir() -> Path:
    """Authoritative app data root: %USERPROFILE%\\.ebook_translator"""
    d = Path.home() / ".ebook_translator"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir_for(source: Path) -> Path:
    """Writable assets dir under user data (not beside the ebook / EXE)."""
    d = data_dir() / "tmp" / f"assets_{source.stem}_{uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ebook_filetypes(ebook_label: str, epub_label: str, all_label: str) -> list[tuple[str, str]]:
    """File dialog patterns. Windows uses ';' between patterns in one filter."""
    if sys.platform == "win32":
        return [
            (ebook_label, "*.epub;*.txt"),
            (epub_label, "*.epub"),
            ("TXT", "*.txt"),
            (all_label, "*.*"),
        ]
    return [
        (ebook_label, "*.epub *.txt"),
        (epub_label, "*.epub"),
        ("TXT", "*.txt"),
        (all_label, "*.*"),
    ]
