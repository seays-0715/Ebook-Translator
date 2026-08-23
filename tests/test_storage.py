"""Storage round-trip tests."""

from pathlib import Path

from src.core.storage import Storage
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
from src.models.job import JobConfig, JobStatus, TranslationJob


def test_book_roundtrip(tmp_path: Path):
    db = tmp_path / "t.db"
    store = Storage(db)
    book = CanonicalBook(
        metadata=BookMetadata(title="Hello", author="A", language="en"),
        chapters=[
            Chapter(
                id="ch1",
                title="C1",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="hi"
                    )
                ],
            )
        ],
    )
    bid = store.save_book(book)
    loaded = store.load_book(bid)
    assert loaded.metadata.title == "Hello"
    assert loaded.chapters[0].blocks[0].text == "hi"


def test_job_and_chunks(tmp_path: Path):
    from src.models.chunk import Chunk, ChunkStatus
    from datetime import datetime, timezone

    db = tmp_path / "t.db"
    store = Storage(db)
    book = CanonicalBook(
        metadata=BookMetadata(title="J"),
        chapters=[
            Chapter(
                id="ch1",
                title="C",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="x"
                    )
                ],
            )
        ],
    )
    book_id = store.save_book(book)
    job = TranslationJob(
        job_id="job1",
        status=JobStatus.PENDING,
        config=JobConfig(target_language="zh-TW"),
        book=book,
        storage_dir=str(tmp_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    object.__setattr__(job, "_book_id", book_id)
    store.save_job(job)
    chunk = Chunk(
        chunk_id="c1",
        chapter_id="ch1",
        block_ids=["p0"],
        source_texts={"p0": "x"},
        status=ChunkStatus.PENDING,
    )
    store.save_chunks("job1", [chunk])
    loaded = store.load_job("job1")
    assert loaded.status == JobStatus.PENDING
    chunks = store.load_chunks("job1")
    assert len(chunks) == 1
    assert chunks[0].source_texts["p0"] == "x"
