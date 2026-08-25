"""Queue lifecycle: status transitions, remove/pause/cancel/retry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue, QueueError


def _make_queue(tmp_path: Path) -> BatchQueue:
    storage = Storage(tmp_path / "app.db")
    return BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )


def test_queue_remove_pending(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    assert len(q.items()) == 1
    q.remove(item.item_id)
    assert len(q.items()) == 0


def test_remove_rejects_processing(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PROCESSING
    with pytest.raises(QueueError, match="PROCESSING"):
        q.remove(item.item_id)
    assert len(q.items()) == 1


def test_remove_completed_and_cancelled(tmp_path: Path):
    q = _make_queue(tmp_path)
    a = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    b = q.add(tmp_path / "b.epub", tmp_path / "b.out.epub")
    c = q.add(tmp_path / "c.epub", tmp_path / "c.out.epub")
    a.status = JobStatus.COMPLETED
    b.status = JobStatus.COMPLETED_WITH_ERRORS
    c.status = JobStatus.CANCELLED
    q.remove(a.item_id)
    q.remove(b.item_id)
    q.remove(c.item_id)
    assert len(q.items()) == 0


def test_remove_delete_job_data(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    from src.models.book import BookMetadata, CanonicalBook, Layout
    from src.models.job import TranslationJob

    job_id = "job-" + uuid4().hex[:8]
    book = CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[],
        assets={},
    )
    q.storage.save_book(book, book_id=job_id)
    job = TranslationJob(job_id=job_id, book=book, status=JobStatus.COMPLETED)
    q.storage.save_job(job)
    item.job_id = job_id
    item.status = JobStatus.COMPLETED
    q.remove(item.item_id, delete_job_data=True)
    with pytest.raises(KeyError):
        q.storage.load_job(job_id)


def test_remove_delete_failure_keeps_item(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.job_id = "job-missing"
    item.status = JobStatus.COMPLETED
    with pytest.raises(Exception):
        q.remove(item.item_id, delete_job_data=True)
    assert len(q.items()) == 1
    assert q.items()[0].status == JobStatus.COMPLETED


def test_queue_cancel_pending(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    q.cancel_job(item.item_id)
    assert q.items()[0].status == JobStatus.CANCELLED


def test_cancel_paused(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PAUSED
    q.cancel(item.item_id)
    assert item.status == JobStatus.CANCELLED


def test_cancel_pending_persistence_failure_keeps_state(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.job_id = "job-missing"
    with pytest.raises(Exception):
        q.cancel(item.item_id)
    assert item.status == JobStatus.PENDING


def test_pause_job_calls_request_pause_on_engine(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PROCESSING
    engine = MagicMock()
    q._current_engine = engine
    q._current_item_id = item.item_id
    q.pause_job(item.item_id)
    engine.request_pause.assert_called_once()


def test_pause_job_rejects_pending(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    with pytest.raises(QueueError, match="PROCESSING"):
        q.pause_job(item.item_id)


def test_pause_processing_without_engine_is_rejected(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PROCESSING
    with pytest.raises(QueueError, match="active TranslationEngine"):
        q.pause_job(item.item_id)
    assert item.status == JobStatus.PROCESSING


def test_cancel_processing_calls_request_stop(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PROCESSING
    engine = MagicMock()
    q._current_engine = engine
    q._current_item_id = item.item_id
    q.cancel(item.item_id)
    engine.request_stop.assert_called_once()
    assert item.status == JobStatus.PROCESSING


def test_cancel_processing_without_engine_is_rejected(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PROCESSING
    with pytest.raises(QueueError, match="active TranslationEngine"):
        q.cancel(item.item_id)
    assert item.status == JobStatus.PROCESSING


def test_queue_resume_cancelled_is_rejected(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    q.cancel_job(item.item_id)
    with pytest.raises(QueueError, match="only for PAUSED"):
        q.resume_job(item.item_id)
    assert item.status == JobStatus.CANCELLED


def test_resume_paused_to_pending(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PAUSED
    q.resume_job(item.item_id)
    assert item.status == JobStatus.PENDING


def test_resume_persistence_failure_keeps_state(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PAUSED
    item.job_id = "job-missing"
    with pytest.raises(Exception):
        q.resume_job(item.item_id)
    assert item.status == JobStatus.PAUSED


def test_retry_job_reuses_job_id(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.COMPLETED_WITH_ERRORS
    item.error = "export_failed: disk full"
    item.job_id = "job-" + uuid4().hex[:8]
    frozen = item.job_id
    q.retry_job(item.item_id)
    assert item.status == JobStatus.PENDING
    assert item.error is None
    assert item.job_id == frozen


def test_retry_persistence_failure_keeps_state(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.COMPLETED_WITH_ERRORS
    item.error = "failed"
    item.job_id = "job-missing"
    with pytest.raises(Exception):
        q.retry_job(item.item_id)
    assert item.status == JobStatus.COMPLETED_WITH_ERRORS
    assert item.error == "failed"


def test_retry_rejects_wrong_status(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "b.epub", tmp_path / "b.out.epub")
    item.status = JobStatus.COMPLETED
    item.job_id = "x"
    with pytest.raises(QueueError):
        q.retry_job(item.item_id)


def test_pause_one_job_does_not_affect_other(tmp_path: Path):
    q = _make_queue(tmp_path)
    a = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    b = q.add(tmp_path / "b.epub", tmp_path / "b.out.epub")
    a.status = JobStatus.PROCESSING
    b.status = JobStatus.PENDING
    engine = MagicMock()
    q._current_engine = engine
    q._current_item_id = a.item_id
    q.pause_job(a.item_id)
    engine.request_pause.assert_called_once()
    assert b.status == JobStatus.PENDING


def test_no_jobstatus_failed_in_module():
    import inspect
    from src.queue import batch_queue as bq

    src = inspect.getsource(bq)
    assert "JobStatus.FAILED" not in src


def test_queue_add_with_book_snapshot(tmp_path: Path):
    from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
    from src.models.blocks import BlockType, ContentBlock

    book = CanonicalBook(
        metadata=BookMetadata(title="Snap Book", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[
            Chapter(
                id="ch1",
                title="Only Chapter",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="Hi"
                    )
                ],
            )
        ],
        assets={},
    )
    q = _make_queue(tmp_path)
    item = q.add(
        tmp_path / "ignored.epub",
        tmp_path / "out.epub",
        book=book,
        display_name="Snap Book",
    )
    assert item.book is not None
    assert item.display_name == "Snap Book"
