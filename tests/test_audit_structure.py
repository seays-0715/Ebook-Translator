"""Regression: cover/front-matter separation, chapter titles, paragraphs, prompts, output dir."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ebooklib import epub

from src.core.settings import AppSettings, TranslationSettings, OutputSettings
from src.epub.generator import generate_epub, _css
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.chapter_detect import _is_technical_filename
from src.parsers.epub_parser import parse_epub
from src.translation.prompts import (
    FICTION_DEFAULT_PROMPT,
    NONFICTION_DEFAULT_PROMPT,
    default_prompt_for_style,
    resolve_system_prompt,
)
from src.ui.paths import app_dir, default_output_dir, resolve_output_dir


def _make_light_novel_fixture(path: Path) -> Path:
    book = epub.EpubBook()
    book.set_identifier("fixture-ln-001")
    book.set_title("Distant Childhood Friends")
    book.set_language("ja")
    book.add_author("Test Author")
    cover_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    book.set_cover("cover.jpg", cover_bytes)

    def xhtml(title: str, body: str, fname: str) -> epub.EpubHtml:
        item = epub.EpubHtml(title=title, file_name=fname, lang="ja")
        item.set_content(
            (
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
                + title
                + "</title></head><body>"
                + body
                + "</body></html>"
            ).encode("utf-8")
        )
        return item

    titlepage = xhtml(
        "Title Page",
        "<h1>Distant Childhood Friends</h1>"
        "<p>Test Author</p>"
        "<p>Cover Illustration</p>"
        '<img src="cover.jpg" alt="cover"/>',
        "p-titlepage.xhtml",
    )
    ch1 = xhtml(
        "Chapter 1 Trying Something New",
        "<h1>Chapter 1 Trying Something New</h1>"
        "<p>First real paragraph of the story begins here.</p>"
        "<p>Second paragraph continues the narrative.</p>"
        "<p>Third paragraph keeps spacing readable.</p>",
        "p-005.xhtml",
    )
    ch2 = xhtml(
        "Chapter 2 Next Day",
        "<h1>Chapter 2 Next Day</h1>"
        "<p>Morning light through the window.</p>"
        "<p>Dialogue starts on this page.</p>",
        "chap_0004.xhtml",
    )
    for item in (titlepage, ch1, ch2):
        book.add_item(item)
    book.toc = (
        epub.Link("p-005.xhtml", "Chapter 1 Trying Something New", "c1"),
        epub.Link("chap_0004.xhtml", "Chapter 2 Next Day", "c2"),
    )
    book.spine = ["nav", titlepage, ch1, ch2]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(path), book, {})
    return path


def test_front_matter_not_in_chapter_one(tmp_path: Path):
    src = _make_light_novel_fixture(tmp_path / "ln.epub")
    result = parse_epub(src, assets_dir=tmp_path / "assets")
    book = result.book
    assert book.chapters
    ch1 = book.chapters[0]
    assert not _is_technical_filename(ch1.title)
    assert "Chapter 1" in ch1.title or "Trying" in ch1.title
    blob = " ".join((b.text or "") for b in ch1.blocks)
    assert "Cover Illustration" not in blob
    images = [b for b in ch1.blocks if b.type == BlockType.IMAGE]
    assert len(images) == 0
    assert any("First real paragraph" in (b.text or "") for b in ch1.blocks)


def test_original_chapter_order_and_titles(tmp_path: Path):
    src = _make_light_novel_fixture(tmp_path / "ln2.epub")
    result = parse_epub(src, assets_dir=tmp_path / "assets2")
    titles = [ch.title for ch in result.book.chapters]
    assert len(titles) >= 2
    for t in titles:
        assert not _is_technical_filename(t), t
        assert not t.upper().startswith("P00")
        assert "chap_" not in t.lower()
    joined = " | ".join(titles)
    assert "Chapter 1" in joined and "Chapter 2" in joined
    i1 = next(i for i, t in enumerate(titles) if "Chapter 1" in t)
    i2 = next(i for i, t in enumerate(titles) if "Chapter 2" in t)
    assert i1 < i2


def test_paragraphs_remain_meaningful(tmp_path: Path):
    src = _make_light_novel_fixture(tmp_path / "ln3.epub")
    result = parse_epub(src, assets_dir=tmp_path / "assets3")
    paras = [
        b.text.strip()
        for ch in result.book.chapters
        for b in ch.blocks
        if b.type == BlockType.PARAGRAPH and (b.text or "").strip()
    ]
    assert len(paras) >= 3
    assert any("First real paragraph" in p for p in paras)
    assert any("Second paragraph" in p for p in paras)
    assert not any(
        "First real paragraph" in p and "Second paragraph" in p for p in paras
    )


def test_br_produces_readable_paragraphs(tmp_path: Path):
    book = epub.EpubBook()
    book.set_identifier("br1")
    book.set_title("BR")
    book.set_language("en")
    c = epub.EpubHtml(title="C", file_name="c.xhtml", lang="en")
    c.set_content(
        (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            "<p>Line A<br/>Line B<br/>Line C</p>"
            "<p>Standalone paragraph after.</p>"
            "</body></html>"
        ).encode("utf-8")
    )
    book.add_item(c)
    book.toc = (c,)
    book.spine = ["nav", c]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    src = tmp_path / "br.epub"
    epub.write_epub(str(src), book, {})
    result = parse_epub(src, assets_dir=tmp_path / "br_assets")
    texts = [
        (b.text or "").strip()
        for ch in result.book.chapters
        for b in ch.blocks
        if b.type == BlockType.PARAGRAPH and (b.text or "").strip()
    ]
    assert any("Line A" in t for t in texts)
    assert any("Standalone paragraph" in t for t in texts)
    assert len(texts) >= 2


def test_style_prompt_shows_builtin_when_no_custom():
    assert default_prompt_for_style("fiction") == FICTION_DEFAULT_PROMPT
    assert default_prompt_for_style("nonfiction") == NONFICTION_DEFAULT_PROMPT
    assert FICTION_DEFAULT_PROMPT != NONFICTION_DEFAULT_PROMPT
    s = TranslationSettings(style="fiction", fiction_prompt="", nonfiction_prompt="")
    assert resolve_system_prompt(s.style, s.fiction_prompt) == FICTION_DEFAULT_PROMPT
    s2 = TranslationSettings(style="nonfiction", nonfiction_prompt="CUSTOM")
    assert resolve_system_prompt("nonfiction", s2.nonfiction_prompt) == "CUSTOM"


def test_conversion_modes_differ_structurally_and_css(tmp_path: Path):
    book = CanonicalBook(
        metadata=BookMetadata(title="T", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[
            Chapter(
                id="ch1",
                title="Chapter 1",
                order=0,
                blocks=[
                    ContentBlock(
                        id="h2", type=BlockType.HEADING, order=0, text="Deep", level=3
                    ),
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=1, text="Body."
                    ),
                ],
            )
        ],
    )
    assert _css(Layout.HORIZONTAL, "preserve") != _css(Layout.HORIZONTAL, "clean")
    out_s = tmp_path / "s.epub"
    generate_epub(book, out_s, conversion_mode="simplified")
    with zipfile.ZipFile(out_s) as zf:
        xhtml = next(n for n in zf.namelist() if n.endswith(".xhtml") and "chap" in n)
        body = zf.read(xhtml).decode("utf-8")
        assert "<h3>" not in body
        assert "Deep" in body


def test_default_output_dir_is_app_output():
    d = default_output_dir()
    assert d.name == "output"
    assert d.parent == app_dir()
    assert resolve_output_dir("") == default_output_dir()
    assert resolve_output_dir(None) == default_output_dir()


def test_settings_output_dir_field():
    s = OutputSettings(default_dir="")
    assert s.default_dir == ""
    app = AppSettings(output=OutputSettings(default_dir="/tmp/custom_out"))
    assert app.output.default_dir == "/tmp/custom_out"
