"""Basic unit tests for core models and chunker."""

from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
from src.translation.chunker import build_chunks, estimate_tokens
from src.translation.validator import validate_ai_response


def _sample_book(n_paragraphs: int = 20) -> CanonicalBook:
    blocks = [
        ContentBlock(
            id=f"p{i}",
            type=BlockType.PARAGRAPH,
            order=i,
            text=f"This is paragraph number {i}. " * 5,
        )
        for i in range(n_paragraphs)
    ]
    return CanonicalBook(
        metadata=BookMetadata(title="Test", author="T", language="en"),
        chapters=[Chapter(id="ch1", title="Chapter 1", order=0, blocks=blocks)],
    )


def test_content_block_translatable():
    p = ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=0, text="hello")
    img = ContentBlock(id="i1", type=BlockType.IMAGE, order=1, image_ref="x")
    assert p.is_translatable()
    assert not img.is_translatable()


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") > 0
    assert estimate_tokens("你好世界") > 0


def test_build_chunks_respects_blocks():
    book = _sample_book(30)
    chunks = build_chunks(book, target_tokens=50)
    assert len(chunks) >= 1
    all_ids = []
    for c in chunks:
        all_ids.extend(c.block_ids)
        assert c.chapter_id == "ch1"
        assert c.status.value == "pending"
    assert len(all_ids) == len(set(all_ids))
    assert len(all_ids) == 30


def test_validate_ai_response_ok():
    src = ["p1", "p2"]
    payload = {
        "translations": [
            {"id": "p1", "text": "譯文一"},
            {"id": "p2", "text": "譯文二"},
        ]
    }
    r = validate_ai_response(src, payload)
    assert r.ok
    assert r.translations["p1"] == "譯文一"


def test_validate_ai_response_missing():
    src = ["p1", "p2"]
    payload = {"translations": [{"id": "p1", "text": "only one"}]}
    r = validate_ai_response(src, payload)
    assert not r.ok
    assert any("Missing" in e for e in r.errors)
