from src.core.chapter_ops import (
    ChapterOpError,
    merge_adjacent,
    remove_chapter,
    rename_chapter,
    split_chapter,
)
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
import pytest


def _book() -> CanonicalBook:
    def paras(prefix: str, n: int):
        return [
            ContentBlock(
                id=f"{prefix}{i}", type=BlockType.PARAGRAPH, order=i, text=f"{prefix}-{i}"
            )
            for i in range(n)
        ]

    return CanonicalBook(
        metadata=BookMetadata(title="T"),
        chapters=[
            Chapter(id="ch1", title="One", order=0, blocks=paras("a", 3)),
            Chapter(id="ch2", title="Two", order=1, blocks=paras("b", 2)),
            Chapter(id="ch3", title="Three", order=2, blocks=paras("c", 2)),
        ],
    )


def test_rename():
    b = rename_chapter(_book(), "ch2", "第二章")
    assert b.chapters[1].title == "第二章"


def test_remove():
    b = remove_chapter(_book(), "ch2")
    assert [c.id for c in b.chapters] == ["ch1", "ch3"]
    assert b.chapters[1].order == 1


def test_merge_adjacent():
    b = merge_adjacent(_book(), "ch1", "ch2", new_title="1+2")
    assert len(b.chapters) == 2
    assert b.chapters[0].title == "1+2"
    assert len(b.chapters[0].blocks) == 5


def test_merge_non_adjacent_fails():
    with pytest.raises(ChapterOpError):
        merge_adjacent(_book(), "ch1", "ch3")


def test_split():
    b = split_chapter(_book(), "ch1", at_block_id="a2")
    assert len(b.chapters) == 4
    assert len(b.chapters[0].blocks) == 2  # a0, a1
    assert b.chapters[1].blocks[0].id == "a2"
