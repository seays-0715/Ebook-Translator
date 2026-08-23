from pathlib import Path

from src.epub.generator import generate_epub
from src.epub.validator import validate_epub_file
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
from src.models.chunk import Chunk, ChunkStatus
from src.translation.book_validator import validate_canonical_book


def test_level2_structure():
    book = CanonicalBook(
        metadata=BookMetadata(title="t"),
        chapters=[
            Chapter(
                id="ch1",
                title="C",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="hi"
                    )
                ],
            )
        ],
    )
    r = validate_canonical_book(book)
    assert r.ok


def test_level2_missing_translation():
    book = CanonicalBook(
        metadata=BookMetadata(title="t"),
        chapters=[
            Chapter(
                id="ch1",
                title="C",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="hi"
                    )
                ],
            )
        ],
    )
    chunks = [
        Chunk(
            chunk_id="c1",
            chapter_id="ch1",
            block_ids=["p0"],
            source_texts={"p0": "hi"},
            status=ChunkStatus.FAILED,
            error_message="boom",
        )
    ]
    r = validate_canonical_book(book, chunks=chunks, require_translations=True)
    assert not r.ok
    assert any("failed" in e.lower() for e in r.errors)


def test_level3_epub(tmp_path: Path):
    book = CanonicalBook(
        metadata=BookMetadata(title="Hello", language="en"),
        chapters=[
            Chapter(
                id="ch1",
                title="Ch1",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="body"
                    )
                ],
            )
        ],
    )
    out = tmp_path / "t.epub"
    generate_epub(book, out)
    r = validate_epub_file(out)
    assert r.ok, r.errors
