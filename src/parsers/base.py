"""Parser result and shared helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.book import CanonicalBook


@dataclass
class ParseResult:
    book: CanonicalBook
    source_path: Path
    warnings: list[str] = field(default_factory=list)
    # Suggested chapters for Preview UI (may be edited by user)
    chapter_suggestions: list[dict] = field(default_factory=list)
