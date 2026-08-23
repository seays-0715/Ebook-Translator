"""Queue lifecycle: add / cancel / remove / resume."""

from __future__ import annotations

from pathlib import Path

from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue


def test_queue_remove_pending(tmp_path: Path):
    storage = Storage(tmp_path / "app.db")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    assert len(q.items()) == 1
    q.remove(item.item_id)
    assert len(q.items()) == 0


def test_queue_cancel_pending(tmp_path: Path):
    storage = Storage(tmp_path / "app.db")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    q.cancel_job(item.item_id)
    assert q.items()[0].status == JobStatus.CANCELLED


def test_queue_resume_job(tmp_path: Path):
    storage = Storage(tmp_path / "app.db")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )
    item = q.add(tmp_path / "a.epub", tmp_path / "a.out.epub")
    q.cancel_job(item.item_id)
    q.resume_job(item.item_id)
    assert q.items()[0].status == JobStatus.PENDING


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
    storage = Storage(tmp_path / "app.db")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )
    item = q.add(
        tmp_path / "ignored.epub",
        tmp_path / "out.epub",
        book=book,
        display_name="Snap Book",
    )
    assert item.book is not None
    assert item.display_name == "Snap Book"
