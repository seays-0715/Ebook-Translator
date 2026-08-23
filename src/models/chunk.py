"""Chunk model for translation pipeline.

Chunk boundaries respect:
1. Block boundaries (never split mid-block)
2. Prefer not splitting continuous dialogue
3. Chapter boundaries preferred over chunk size
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChunkStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Chunk(BaseModel):
    chunk_id: str
    chapter_id: str
    block_ids: list[str] = Field(
        ...,
        description="Ordered list of block ids included in this chunk",
    )
    # Carry-over is read-only reference context; not re-translated
    carry_over_source: list[dict[str, str]] = Field(
        default_factory=list,
        description="[{id, text}, ...] from previous chunk tail",
    )
    carry_over_translated: list[dict[str, str]] = Field(default_factory=list)
    source_texts: dict[str, str] = Field(
        default_factory=dict,
        description="block_id -> source text",
    )
    translated_texts: dict[str, str] = Field(
        default_factory=dict,
        description="block_id -> translated text (filled after success)",
    )
    status: ChunkStatus = ChunkStatus.PENDING
    error_message: str | None = None
    attempt_count: int = 0
    token_estimate: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
