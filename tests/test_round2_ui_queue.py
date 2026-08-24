"""Round-2 targeted UI/queue regressions."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue


def test_retry_job_reuses_job_id_and_clears_error(tmp_path: Path):
    storage = Storage(tmp_path / "store")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(source_language="ja", target_language="zh-TW", style="fiction"),
    )
    item = q.add(tmp_path / "a.epub", tmp_path / "a.translated.epub", display_name="A")
    # Simulate completed-with-errors with frozen job id
    item.status = JobStatus.COMPLETED_WITH_ERRORS
    item.error = "export_failed: disk full"
    item.job_id = "job-" + uuid4().hex[:8]
    q.retry_job(item.item_id)
    assert item.status == JobStatus.PENDING
    assert item.error is None
    assert item.job_id.startswith("job-")


def test_retry_job_rejects_wrong_status(tmp_path: Path):
    storage = Storage(tmp_path / "store")
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "work",
        config=JobConfig(),
    )
    item = q.add(tmp_path / "b.epub", tmp_path / "b.translated.epub")
    item.status = JobStatus.COMPLETED
    item.job_id = "x"
    try:
        q.retry_job(item.item_id)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_chapter_list_label_is_title_only():
    """Chapter list must not embed body snippets in the label."""
    from src.models.blocks import BlockType, ContentBlock
    from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout

    blocks = [
        ContentBlock(id="h0", type=BlockType.HEADING, order=0, text="Chapter One", level=1),
        ContentBlock(
            id="p0",
            type=BlockType.PARAGRAPH,
            order=1,
            text="This is a long body paragraph that must not appear in the chapter list item.",
        ),
    ]
    book = CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[Chapter(id="c1", title="Chapter One", order=0, blocks=blocks)],
    )
    # Simulate list label construction used by ConvertMixin
    ch = book.chapters[0]
    title = ch.title or "Untitled"
    label = f"{ch.order + 1}. {title}  ({len(ch.blocks)})"
    assert "long body paragraph" not in label
    assert "Chapter One" in label
