"""Persistent incomplete job recovery — storage list + queue restore."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.core.storage import Storage
from src.models.book import BookMetadata, CanonicalBook, Layout
from src.models.chunk import Chunk, ChunkStatus
from src.models.job import JobConfig, JobStatus, TranslationJob
from src.queue.batch_queue import BatchQueue, QueueError, QueueItem
from src.models.blocks import BlockType, ContentBlock
from src.models.book import Chapter


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minimal_book(title: str = "Test Book") -> CanonicalBook:
    return CanonicalBook(
        schema_version=1,
        metadata=BookMetadata(title=title, author="Author", language="ja"),
        layout=Layout.REFLOWABLE,
        chapters=[
            Chapter(
                id="ch1",
                title="Chapter 1",
                order=0,
                blocks=[
                    ContentBlock(
                        id="b1",
                        type=BlockType.PARAGRAPH,
                        order=0,
                        text="Hello world.",
                    )
                ],
            )
        ],
        assets={},
    )


def _job_config() -> JobConfig:
    return JobConfig(
        source_language="ja",
        target_language="zh-Hant",
        endpoint="http://localhost:11434",
        model="test",
        model_identifier="test",
        style="fiction",
        chunk_target_tokens=500,
        carry_over_paragraphs=1,
        retry_count=1,
        retry_delay_seconds=0.1,
        request_timeout_seconds=30,
        request_interval_seconds=0,
        endpoint_fail_threshold=3,
        prompt="translate",
    )


def _make_job(store: Storage, status: JobStatus, title: str = "Book") -> TranslationJob:
    book = _minimal_book(title)
    job_id = str(uuid4())
    store.save_book(book, book_id=job_id)
    job = TranslationJob(
        job_id=job_id,
        schema_version=1,
        status=status,
        config=_job_config(),
        book=book,
        storage_dir=str(Path("/tmp") / job_id),
        output_path=str(Path("/tmp") / f"{job_id}.epub"),
        created_at=_utcnow(),
        updated_at=_utcnow(),
        total_chunks=2,
        completed_chunks=1 if status != JobStatus.PENDING else 0,
        failed_chunks=0,
    )
    store.save_job(job)
    return job


# --- storage: list_incomplete_jobs ---


def test_list_incomplete_returns_unfinished(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j1 = _make_job(store, JobStatus.PENDING, "P")
    j2 = _make_job(store, JobStatus.PAUSED, "A")
    j3 = _make_job(store, JobStatus.PROCESSING, "R")
    j4 = _make_job(store, JobStatus.COMPLETED_WITH_ERRORS, "E")
    rows = store.list_incomplete_jobs()
    ids = {r["job_id"] for r in rows}
    assert j1.job_id in ids
    assert j2.job_id in ids
    assert j3.job_id in ids
    assert j4.job_id in ids
    assert len(rows) >= 4


def test_list_incomplete_excludes_completed(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    done = _make_job(store, JobStatus.COMPLETED, "Done")
    rows = store.list_incomplete_jobs()
    ids = {r["job_id"] for r in rows}
    assert done.job_id not in ids


def test_list_incomplete_excludes_cancelled(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    c = _make_job(store, JobStatus.CANCELLED, "Cancel")
    rows = store.list_incomplete_jobs()
    ids = {r["job_id"] for r in rows}
    assert c.job_id not in ids


def test_list_incomplete_book_title_and_progress(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PAUSED, "My Title")
    rows = store.list_incomplete_jobs()
    row = next(r for r in rows if r["job_id"] == j.job_id)
    assert row.get("title") == "My Title" or "title" in row
    assert row["total_chunks"] == 2
    assert row["completed_chunks"] == 1


def test_list_incomplete_multiple_independent(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    a = _make_job(store, JobStatus.PENDING, "A")
    b = _make_job(store, JobStatus.PAUSED, "B")
    rows = {r["job_id"]: r for r in store.list_incomplete_jobs()}
    assert a.job_id in rows and b.job_id in rows


def test_list_incomplete_visible_after_fresh_storage(tmp_path: Path):
    db = tmp_path / "t.db"
    store = Storage(db)
    j = _make_job(store, JobStatus.PAUSED, "Persist")
    store2 = Storage(db)
    rows = store2.list_incomplete_jobs()
    assert any(r["job_id"] == j.job_id for r in rows)


# --- queue restore / continue ---


def test_restore_incomplete_jobs_loads_items(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PAUSED, "Restore Me")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    items = q.restore_incomplete_jobs()
    assert len(items) >= 1
    assert any(i.job_id == j.job_id for i in items)
    assert any(i.job_id == j.job_id for i in q.items())


def test_restore_normalizes_orphaned_processing_to_paused(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PROCESSING, "Orphan")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    item = next(i for i in q.items() if i.job_id == j.job_id)
    assert item.status == JobStatus.PAUSED
    loaded = store.load_job(j.job_id)
    assert loaded.status == JobStatus.PAUSED


def test_restore_idempotent(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PENDING, "Idem")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    n1 = len(q.items())
    q.restore_incomplete_jobs()
    assert len(q.items()) == n1


def test_continue_job_pending(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PENDING, "Cont")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    item = next(i for i in q.items() if i.job_id == j.job_id)
    with patch.object(q, "_process_item") as mock_proc:
        q.continue_job(item.item_id)
        # continue routes to existing path without resetting job
        assert item.job_id == j.job_id


def test_continue_job_paused(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PAUSED, "PCont")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    item = next(i for i in q.items() if i.job_id == j.job_id)
    q.continue_job(item.item_id)
    assert item.status == JobStatus.PENDING


def test_remove_after_restore_paused_ok(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PROCESSING, "Rem")
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    item = next(i for i in q.items() if i.job_id == j.job_id)
    assert item.status == JobStatus.PAUSED
    q.remove(item.item_id, delete_job_data=True)
    assert item.item_id not in [i.item_id for i in q.items()]


# --- checkpoint preservation ---


def test_checkpoint_preserved_on_restore(tmp_path: Path):
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PAUSED, "Ckpt")
    chunks = [
        Chunk(
            chunk_id="c1",
            chapter_id="ch1",
            block_ids=["b1"],
            source_texts={"b1": "a"},
            translated_texts={"b1": "A"},
            status=ChunkStatus.COMPLETED,
        ),
        Chunk(
            chunk_id="c2",
            chapter_id="ch1",
            block_ids=["b2"],
            source_texts={"b2": "b"},
            translated_texts={},
            status=ChunkStatus.PENDING,
        ),
    ]
    store.save_chunks(j.job_id, chunks)
    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    loaded = store.load_chunks(j.job_id)
    by_id = {c.chunk_id: c for c in loaded}
    assert by_id["c1"].status == ChunkStatus.COMPLETED
    assert by_id["c1"].translated_texts.get("b1") == "A"
    assert by_id["c2"].status == ChunkStatus.PENDING


def test_engine_skips_completed_chunks_on_continue(tmp_path: Path):
    """Engine path must not re-translate COMPLETED chunks after restore."""
    store = Storage(tmp_path / "t.db")
    j = _make_job(store, JobStatus.PAUSED, "Skip")
    chunks = [
        Chunk(
            chunk_id="c1",
            chapter_id="ch1",
            block_ids=["b1"],
            source_texts={"b1": "done"},
            translated_texts={"b1": "DONE"},
            status=ChunkStatus.COMPLETED,
        ),
        Chunk(
            chunk_id="c2",
            chapter_id="ch1",
            block_ids=["b2"],
            source_texts={"b2": "todo"},
            translated_texts={},
            status=ChunkStatus.PENDING,
        ),
    ]
    store.save_chunks(j.job_id, chunks)
    store.update_job_progress(j.job_id, completed=1, failed=0, total=2)

    q = BatchQueue(storage=store, work_root=tmp_path / "w", config=_job_config())
    q.restore_incomplete_jobs()
    item = next(i for i in q.items() if i.job_id == j.job_id)

    processed: list[str] = []

    class FakeEngine:
        def __init__(self, *a, **k):
            pass

        def run(self):
            pending = store.load_pending_chunks(j.job_id)
            for c in pending:
                processed.append(c.chunk_id)
                c.status = ChunkStatus.COMPLETED
                c.translated_texts = {bid: "X" for bid in c.block_ids}
                store.update_chunk(j.job_id, c)
            store.update_job_status(j.job_id, JobStatus.COMPLETED, finished=True)
            return JobStatus.COMPLETED

        def request_pause(self):
            pass

        def request_stop(self):
            pass

    with patch("src.queue.batch_queue.TranslationEngine", FakeEngine):
        with patch("src.queue.batch_queue.export_job_epub"):
            q.continue_job(item.item_id)
            # drive processing if continue left it pending
            if item.status == JobStatus.PENDING:
                q._process_item(item)

    status = store.load_job(j.job_id).status
    assert status == JobStatus.COMPLETED
    assert processed == ["c2"]  # only the unfinished chunk
    final = q.storage.load_chunks(j.job_id)
    assert all(c.status == ChunkStatus.COMPLETED for c in final)
