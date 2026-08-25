"""Queue lifecycle: status transitions, remove/pause/cancel/retry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
    job_id = item.job_id or ("job-" + uuid4().hex[:8])
    book = _book()
    q.storage.save_book(book, book_id=job_id)
    q.storage.save_job(TranslationJob(job_id=job_id, book=book, status=status))
    item.job_id = job_id
    return job_id


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
    job_id = _persist_job(q, item, JobStatus.COMPLETED)
    item.status = JobStatus.COMPLETED
    q.remove(item.item_id, delete_job_data=True)
    with pytest.raises(KeyError):
        q.storage.load_job(job_id)


def test_remove_delete_failure_keeps_item(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.job_id = "job-1"
    item.status = JobStatus.COMPLETED
    with patch.object(q.storage, "delete_job", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            q.remove(item.item_id, delete_job_data=True)
    assert q.items()[0].item_id == item.item_id


def test_queue_cancel_pending(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    q.cancel_job(item.item_id)
    assert item.status == JobStatus.CANCELLED


def test_cancel_paused(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    item.status = JobStatus.PAUSED
    q.cancel(item.item_id)
    assert item.status == JobStatus.CANCELLED


def test_cancel_pending_persistence_failure_keeps_state(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    _persist_job(q, item, JobStatus.PENDING)
    with patch.object(q.storage, "update_job_status", side_effect=OSError("db locked")):
        with pytest.raises(OSError, match="db locked"):
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
    _persist_job(q, item, JobStatus.PAUSED)
    with patch.object(q.storage, "update_job_status", side_effect=OSError("db locked")):
        with pytest.raises(OSError, match="db locked"):
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
    item.job_id = "job-1"
    with patch.object(q.storage, "update_job_status", side_effect=OSError("db locked")):
        with pytest.raises(OSError, match="db locked"):
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
    from src.models.blocks import BlockType, ContentBlock
    from src.models.book import Chapter

    book = CanonicalBook(
        metadata=BookMetadata(title="Snap Book", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[
            Chapter(
                id="ch1",
                title="Only Chapter",
                order=0,
                blocks=[ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=0, text="Hi")],
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


def test_export_failure_becomes_completed_with_errors(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub", book=_book())
    _persist_job(q, item, JobStatus.PENDING)

    engine = MagicMock()
    engine.run.return_value = JobStatus.COMPLETED
    with (
        patch("src.queue.batch_queue.TranslationEngine", return_value=engine),
        patch(
            "src.queue.batch_queue.export_job_epub",
            side_effect=OSError("disk full"),
        ),
    ):
        q._process_item(item)

    assert item.status == JobStatus.COMPLETED_WITH_ERRORS
    assert item.error is not None
    assert "export_failed" in item.error
    assert "disk full" in item.error


def test_export_failure_is_persisted(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub", book=_book())
    job_id = _persist_job(q, item, JobStatus.PENDING)

    engine = MagicMock()
    engine.run.return_value = JobStatus.COMPLETED
    with (
        patch("src.queue.batch_queue.TranslationEngine", return_value=engine),
        patch(
            "src.queue.batch_queue.export_job_epub",
            side_effect=OSError("disk full"),
        ),
    ):
        q._process_item(item)

    persisted = q.storage.load_job(job_id)
    assert persisted.status == JobStatus.COMPLETED_WITH_ERRORS
    assert persisted.error_summary is not None
    assert "export_failed" in persisted.error_summary
    assert "disk full" in persisted.error_summary

    reopened = Storage(tmp_path / "app.db")
    disk = reopened.load_job(job_id)
    assert disk.status == JobStatus.COMPLETED_WITH_ERRORS
    assert disk.error_summary is not None
    assert "export_failed" in disk.error_summary


def test_export_failure_persist_fails_keeps_memory_and_sqlite(tmp_path: Path):
    """If COMPLETED_WITH_ERRORS cannot be written, memory must stay COMPLETED."""
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub", book=_book())
    job_id = _persist_job(q, item, JobStatus.PENDING)

    engine = MagicMock()

    def engine_run():
        q.storage.update_job_status(job_id, JobStatus.COMPLETED, finished=True)
        return JobStatus.COMPLETED

    engine.run.side_effect = engine_run

    real_update = q.storage.update_job_status

    def fail_completed_with_errors(job_id_arg, status, *args, **kwargs):
        if status == JobStatus.COMPLETED_WITH_ERRORS:
            raise OSError("db locked")
        return real_update(job_id_arg, status, *args, **kwargs)

    with (
        patch("src.queue.batch_queue.TranslationEngine", return_value=engine),
        patch(
            "src.queue.batch_queue.export_job_epub",
            side_effect=OSError("disk full"),
        ),
        patch.object(q.storage, "update_job_status", side_effect=fail_completed_with_errors),
    ):
        with pytest.raises(OSError, match="db locked"):
            q._process_item(item)

    assert item.status == JobStatus.COMPLETED
    assert item.error is None or "export_failed" not in (item.error or "")
    persisted = q.storage.load_job(job_id)
    assert persisted.status == JobStatus.COMPLETED
    assert persisted.status != JobStatus.COMPLETED_WITH_ERRORS


def test_process_exception_persist_fails_keeps_prior_status(tmp_path: Path):
    """Worker exception path: failed status write must not leave divergent memory."""
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub", book=_book())
    job_id = _persist_job(q, item, JobStatus.PENDING)

    engine = MagicMock()
    engine.run.side_effect = RuntimeError("endpoint down")

    with (
        patch("src.queue.batch_queue.TranslationEngine", return_value=engine),
        patch.object(q.storage, "update_job_status", side_effect=OSError("db locked")),
    ):
        with pytest.raises(OSError, match="db locked"):
            q._process_item(item)

    assert item.status == JobStatus.PROCESSING
    persisted = q.storage.load_job(job_id)
    assert persisted.status == JobStatus.PENDING


def test_cancel_paused_persistence_failure_keeps_paused(tmp_path: Path):
    q = _make_queue(tmp_path)
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    _persist_job(q, item, JobStatus.PAUSED)
    item.status = JobStatus.PAUSED
    with patch.object(q.storage, "update_job_status", side_effect=OSError("db locked")):
        with pytest.raises(OSError, match="db locked"):
            q.cancel(item.item_id)
    assert item.status == JobStatus.PAUSED
    assert q.storage.load_job(item.job_id).status == JobStatus.PAUSED
