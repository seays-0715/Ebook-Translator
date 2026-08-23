"""Canonical Book data model.

Book
├── Metadata
├── Cover
├── Language
├── Layout
└── Chapters
    ├── Title
    └── Blocks[]   (order == reading order)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .blocks import ContentBlock


class Layout(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class BookMetadata(BaseModel):
    title: str = "Untitled"
    author: str = "Unknown"
    language: str = "und"
    identifier: str | None = None
    publisher: str | None = None
    description: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Chapter(BaseModel):
    id: str
    title: str
    order: int = Field(..., ge=0)
    blocks: list[ContentBlock] = Field(default_factory=list)

    def translatable_blocks(self) -> list[ContentBlock]:
        return [b for b in self.blocks if b.is_translatable()]


class CanonicalBook(BaseModel):
    """Normalized, structure-only representation of a book.

    Source of truth for all downstream steps (preview, translate, EPUB gen).
    """

    schema_version: int = 1
    metadata: BookMetadata = Field(default_factory=BookMetadata)
    cover_ref: str | None = None
    layout: Layout = Layout.HORIZONTAL
    chapters: list[Chapter] = Field(default_factory=list)
    # Asset store key -> bytes or path; kept separate for size
    assets: dict[str, str] = Field(
        default_factory=dict,
        description="asset_key -> relative file path under job storage",
    )

    def chapter_by_id(self, chapter_id: str) -> Chapter | None:
        for ch in self.chapters:
            if ch.id == chapter_id:
                return ch
        return None

    def block_by_id(self, block_id: str) -> ContentBlock | None:
        for ch in self.chapters:
            for b in ch.blocks:
                if b.id == block_id:
                    return b
        return None

    def all_translatable_blocks(self) -> list[tuple[str, ContentBlock]]:
        """Return (chapter_id, block) pairs for all translatable content."""
        result: list[tuple[str, ContentBlock]] = []
        for ch in self.chapters:
            for b in ch.blocks:
                if b.is_translatable():
                    result.append((ch.id, b))
        return result

    def total_translatable_count(self) -> int:
        return sum(1 for ch in self.chapters for b in ch.blocks if b.is_translatable())
