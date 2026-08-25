"""BatchQueue lifecycle: status transitions and persistence invariants."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.storage import Storage
from src.models.book import BookMetadata, CanonicalBook, Layout
from src.models.job import JobConfig, JobStatus, TranslationJob
from src.queue.batch_queue import BatchQueue, QueueError


def _make_queue(tmp_path: Path) -> BatchQueue:
    storage = Storage(tmp_path / "app.db")
    return BatchQueue(storage=storage, work_root=tmp_path / "work", config=JobConfig())


def _book() -> CanonicalBook:
    return CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[],
        assets={},
    )


def _persist_job(q: BatchQueue, item, status: JobStatus = JobStatus.PENDING) -> str:
    job_id = item.job_id or f"job-{item.item_id[:8]}"
    item.job_id = job_id
    q.storage.save_book(book, book_id=job_id) if False else None
    book = item.book or _book()
    q.storage.save_book(book, book_id=job_id)
    q.storage.save_job(TranslationJob(job_id=job_id, book=book, status=status))
    return job_id
