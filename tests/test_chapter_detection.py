"""Chapter detection must never use technical spine filenames as titles."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from src.models.blocks import BlockType, ContentBlock
from src.parsers.epub_parser import (
    _assign_chapters,
    _guess_title,
    _is_technical_filename,
    _title_from_blocks,
    parse_epub,
)


def test_technical_filenames_detected():
    assert _is_technical_filename("P001.xhtml")
    assert _is_technical_filename("p002")
    assert _is_technical_filename("item001.xhtml")
    assert _is_technical_filename("item12")
    assert _is_technical_filename("chap_01.xhtml")
    assert _is_technical_filename("section1")
    assert not _is_technical_filename("第一章")
    assert not _is_technical_filename("Chapter One")
    assert not _is_technical_filename("prologue")


def test_guess_title_ignores_technical_fallback():
    soup = BeautifulSoup("<html><body><p>Only body text.</p></body></html>", "lxml")
    assert _guess_title(soup, "P001.xhtml") is None
    assert _guess_title(soup, "item001.xhtml") is None


def test_guess_title_prefers_heading():
    soup = BeautifulSoup(
        "<html><body><h1>第一章 黎明</h1><p>正文</p></body></html>", "lxml"
    )
    assert _guess_title(soup, "P001.xhtml") == "第一章 黎明"


def test_title_from_blocks_heading():
    blocks = [
        ContentBlock(id="h0", type=BlockType.HEADING, order=0, text="第二章", level=1),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="內容"),
    ]
    assert _title_from_blocks(blocks) == "第二章"


def test_assign_chapters_never_uses_p001():
    blocks_a = [
        ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=0, text="續寫文字"),
    ]
    blocks_b = [
        ContentBlock(id="h0", type=BlockType.HEADING, order=0, text="第一章", level=1),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="開始"),
    ]
    chapters = _assign_chapters(
        [
            (None, blocks_a),
            ("第一章", blocks_b),
        ]
    )
    assert chapters[0].title == "Chapter 1"
    assert chapters[0].title != "P001"
    assert "P00" not in chapters[0].title
    assert chapters[1].title == "第一章"


def _write_epub(path: Path, chapters: list[tuple[str, str]]) -> None:
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Test Novel")
    book.set_language("zh")
    book.add_author("Tester")
    items = []
    for fname, body in chapters:
        item = epub.EpubHtml(title=Path(fname).stem, file_name=fname, lang="zh")
        item.set_content(
            f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{body}</body></html>'
        )
        book.add_item(item)
        items.append(item)
    book.spine = ["nav"] + items
    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


def test_parse_epub_p001_not_title(tmp_path: Path):
    path = tmp_path / "novel.epub"
    _write_epub(
        path,
        [
            ("P001.xhtml", "<p>這是延續段落，沒有標題。</p>"),
            ("P002.xhtml", "<h1>第一章</h1><p>正文開始。</p>"),
            ("item001.xhtml", "<p>又一段。</p>"),
        ],
    )
    result = parse_epub(path, assets_dir=tmp_path / "assets")
    titles = [ch.title for ch in result.book.chapters]
    for t in titles:
        assert "P001" not in t
        assert "P002" not in t
        assert "item001" not in t.lower()
    assert any("第一章" in t for t in titles)
