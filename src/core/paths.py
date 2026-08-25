"""App/output path helpers (no GUI imports).

Used by settings and tests. UI-specific helpers (file dialogs, assets) live
in ``src.ui.paths``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory containing the running EXE (frozen) or project root (dev)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
        return Path(sys.executable).resolve().parent
    # Dev: repo root (parent of src/)
    return Path(__file__).resolve().parents[2]


def default_output_dir() -> Path:
    """Default output: <EXE or project dir>/output"""
    d = app_dir() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_output_dir(configured: str | None = None) -> Path:
    """Use configured path if non-empty, else default_output_dir()."""
    if configured and str(configured).strip():
        p = Path(str(configured).strip()).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    return default_output_dir()
