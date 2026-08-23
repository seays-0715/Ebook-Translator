from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
from src.translation.chunker import build_chunks, estimate_tokens
from src.translation.validator import validate_ai_response


def _book_with_n_paras(n: int) -> CanonicalBook:
    blocks = [
        ContentBlock(
            id=f"p{i}", type=BlockType.PARAGRAPH, order=i, text=f"Paragraph {i}. " * 20
        )
        for i in range(n)
    ]
    return CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        chapters=[Chapter(id="ch1", title="Chapter 1", order=0, blocks=blocks)],
    )


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") > 0


def test_build_chunks_respects_chapter_boundary():
    book = _book_with_n_paras(30)
    chunks = build_chunks(book, target_tokens=200, carry_over_paragraphs=2)
    assert chunks
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


def test_validate_ai_response_unexpected_fields():
    src = ["p1"]
    payload = {
        "translations": [{"id": "p1", "text": "ok", "extra": "no"}],
        "meta": "no",
    }
    r = validate_ai_response(src, payload)
    assert not r.ok
    assert any("Unexpected" in e for e in r.errors)
