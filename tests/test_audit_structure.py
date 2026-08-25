"""Regression: cover/front-matter separation, chapter titles, paragraphs, prompts, output dir."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ebooklib import epub

from src.core.paths import app_dir, default_output_dir, resolve_output_dir
from src.core.settings import AppSettings, OutputSettings, TranslationSettings
from src.epub.generator import _css, generate_epub
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.chapter_detect import detect_chapters
from src.parsers.epub_parser import parse_epub
from src.translation.prompts import (
    FICTION_DEFAULT_PROMPT,
    NONFICTION_DEFAULT_PROMPT,
    default_prompt_for_style,
    resolve_system_prompt,
)


def _make_epub(path: Path, chapters_html: list[tuple[str, str]], title: str = "Book") -> None:
    book = epub.EpubBook()
    book.set_identifier("id-struct")
    book.set_title(title)
    book.set_language("en")
    spine = []
    toc = []
    for i, (name, html) in enumerate(chapters_html):
        item = epub.EpubHtml(title=name, file_name=f"c{i}.xhtml", lang="en")
        item.set_content(
            f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{html}</body></html>'
        )
        book.add_item(item)
        spine.append(item)
        toc.append(item)
    book.toc = tuple(toc)
    book.spine = ["nav"] + spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book, {})


def test_front_matter_not_merged_as_chapter(tmp_path: Path):
    src = tmp_path / "fm.epub"
    _make_epub(
        src,
        [
            ("cover", "<p>Cover page</p>"),
            ("Chapter One", "<h1>Chapter One</h1><p>Body text here.</p>"),
        ],
        title="FM",
    )
    result = parse_epub(src, assets_dir=tmp_path / "assets")
    titles = [c.title for c in result.book.chapters]
    assert any("Chapter" in (t or "") for t in titles)


def test_paragraph_boundaries_retained(tmp_path: Path):
    src = tmp_path / "p.epub"
    _make_epub(
        src,
        [("Ch", "<p>First paragraph.</p><p>Second paragraph.</p>")],
    )
    result = parse_epub(src, assets_dir=tmp_path / "assets")
    paras = [
        b.text
        for ch in result.book.chapters
        for b in ch.blocks
        if b.type == BlockType.PARAGRAPH
    ]
    assert "First paragraph." in paras
    assert "Second paragraph." in paras


def test_style_prompts_differ():
    assert default_prompt_for_style("fiction") == FICTION_DEFAULT_PROMPT
    assert default_prompt_for_style("nonfiction") == NONFICTION_DEFAULT_PROMPT
    assert FICTION_DEFAULT_PROMPT != NONFICTION_DEFAULT_PROMPT
    s = TranslationSettings(style="fiction", fiction_prompt="", nonfiction_prompt="")
    assert resolve_system_prompt(s.style, s.fiction_prompt) == FICTION_DEFAULT_PROMPT
    s2 = TranslationSettings(style="nonfiction", nonfiction_prompt="CUSTOM")
    assert resolve_system_prompt("nonfiction", s2.nonfiction_prompt) == "CUSTOM"


def test_conversion_modes_differ_structurally_and_css(tmp_path: Path):
    """Clean keeps deep headings; Compact flattens level>=3 to p.subhead.

    Both retain heading text, chapter structure, and paragraph content.
    """
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
                        id="h2", type=BlockType.HEADING, order=0, text="Section", level=2
                    ),
                    ContentBlock(
                        id="h3", type=BlockType.HEADING, order=1, text="Deep", level=3
                    ),
                    ContentBlock(
                        id="h4", type=BlockType.HEADING, order=2, text="Detail", level=4
                    ),
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=3, text="Body paragraph."
                    ),
                ],
            )
        ],
    )
    assert _css(Layout.HORIZONTAL, "clean") != _css(Layout.HORIZONTAL, "compact")

    out_clean = tmp_path / "clean.epub"
    out_compact = tmp_path / "compact.epub"
    generate_epub(book, out_clean, conversion_mode="clean")
    generate_epub(book, out_compact, conversion_mode="compact")

    def _chapter_body(path: Path) -> str:
        with zipfile.ZipFile(path) as zf:
            xhtml = next(
                n for n in zf.namelist() if n.endswith(".xhtml") and "chap" in n
            )
            return zf.read(xhtml).decode("utf-8")

    body_clean = _chapter_body(out_clean)
    body_compact = _chapter_body(out_compact)

    # Clean: full meaningful heading hierarchy
    assert "<h2>Section</h2>" in body_clean
    assert "<h3>Deep</h3>" in body_clean
    assert "<h4>Detail</h4>" in body_clean
    assert "Body paragraph." in body_clean
    assert 'class="subhead"' not in body_clean

    # Compact: level >= 3 flattened to subhead; content retained
    assert "<h2>Section</h2>" in body_compact
    assert "<h3>" not in body_compact
    assert "<h4>" not in body_compact
    assert 'class="subhead">Deep</p>' in body_compact or ">Deep</p>" in body_compact
    assert "Detail" in body_compact
    assert "Body paragraph." in body_compact
    assert "Chapter 1" in body_compact


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
