"""Translation Job — immutable config snapshot after first execution.

Once a Job starts, its configuration (model, glossary version, prompt, style)
must not change. To use new settings, create a Duplicate / New Job.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .book import CanonicalBook


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    CANCELLED = "cancelled"


class QueueStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class JobConfig(BaseModel):
    """Immutable snapshot of translation settings after first execution.

    Includes glossary *entries* (not a live reference). Resume must use this
    snapshot; callers must not silently replace it with current global glossary.
    """

    source_language: str = "auto"
    target_language: str = "zh-TW"
    model: str = "local"
    endpoint: str = "http://localhost:8000/v1"
    model_identifier: str = ""
    glossary_version: str | None = None
    # Frozen prompt-list snapshot: [{source, target, type?, notes?}, ...]
    glossary_entries: list[dict[str, str]] = Field(default_factory=list)
    prompt: str = ""
    style: str = "natural"
    chunk_target_tokens: int = 1000
    carry_over_paragraphs: int = 2
    retry_count: int = 3
    retry_delay_seconds: float = 2.0
    request_timeout_seconds: float = 120.0
    request_interval_seconds: float = 0.5
    endpoint_fail_threshold: int = 3
    extra: dict[str, Any] = Field(default_factory=dict)


class TranslationJob(BaseModel):
    """Full job record. Book is a complete snapshot (not a shared reference)."""

    job_id: str
    schema_version: int = 1
    status: JobStatus = JobStatus.PENDING
    config: JobConfig = Field(default_factory=JobConfig)
    book: CanonicalBook
    # Paths under job storage root
    storage_dir: str = ""
    output_path: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    # Progress summary (detailed chunk state lives in SQLite)
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    error_summary: str | None = None
