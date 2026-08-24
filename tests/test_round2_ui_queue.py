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
    """Exercise production format_chapter_list_label — title/nav only.

    Must fail if production reintroduces body snippets, block counts,
    or other content statistics into the chapter-list label.
    """
    from src.models.blocks import BlockType, ContentBlock
    from src.models.book import Chapter
    from src.ui._common import format_chapter_list_label

    body = (
        "This is a long body paragraph that must not appear "
        "in the chapter list item."
    )
    blocks = [
        ContentBlock(
            id="h0", type=BlockType.HEADING, order=0, text="Chapter One", level=1
        ),
        ContentBlock(
            id="p0", type=BlockType.PARAGRAPH, order=1, text=body
        ),
    ]
    ch = Chapter(id="c1", title="Chapter One", order=0, blocks=blocks)
    n_blocks = len(ch.blocks)

    label = format_chapter_list_label(ch.order, ch.title)

    assert "Chapter One" in label
    assert body not in label
    assert "long body paragraph" not in label
    # Block count must not appear (e.g. "(2)" or "2 blocks")
    assert f"({n_blocks})" not in label
    assert "blocks" not in label.lower()
    # Parentheses used only for block stats previously — none expected
    assert "(" not in label and ")" not in label
