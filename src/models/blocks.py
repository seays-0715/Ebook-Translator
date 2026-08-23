"""Content Block definitions — the atomic unit of Canonical Book.

Block order within a Chapter IS the reading order.
Translation only mutates `text`; structure fields are immutable after creation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    IMAGE = "image"
    CAPTION = "caption"
    HEADING = "heading"
    FOOTNOTE = "footnote"


class ContentBlock(BaseModel):
    """Unified content unit. Order in Chapter.blocks == reading order."""

    id: str = Field(..., description="Stable unique id within book, e.g. p101, img3")
    type: BlockType
    order: int = Field(..., ge=0, description="0-based position within chapter")
    text: str | None = None
    # Image-specific
    image_ref: str | None = Field(
        default=None,
        description="Relative path or asset key for image blocks",
    )
    image_alt: str | None = None
    # Optional attrs preserved when useful
    level: int | None = Field(
        default=None,
        description="Heading level 1-6 when type==heading",
    )
    attrs: dict[str, Any] = Field(default_factory=dict)

    def is_translatable(self) -> bool:
        return self.type in (
            BlockType.PARAGRAPH,
            BlockType.CAPTION,
            BlockType.HEADING,
            BlockType.FOOTNOTE,
        ) and bool(self.text and self.text.strip())

    def with_text(self, new_text: str) -> ContentBlock:
        """Return a copy with updated text only (structure unchanged)."""
        return self.model_copy(update={"text": new_text})
