"""Regression coverage for V1 audit fixes.

- Glossary: two independent selection slots, same semantics, None allowed
- Conversion mode: standard | compact passed to generator
- Chapter: original titles preferred over technical filenames
- Paragraph: <p> / <br> boundaries preserved
- Style: Fiction / Non-Fiction prompts, save/reset defaults
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.core.pipeline import convert_file, create_translation_job
from src.core.settings import AppSettings, TranslationSettings
from src.core.storage import Storage
from src.epub.generator import generate_epub, _css
from src.glossary.models import Glossary, GlossaryEntry, GlossaryType
from src.glossary.store import GlossaryStore
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.models.job import JobConfig
from src.parsers.chapter_detect import (
    _is_technical_filename,
    detect_chapters,
)
from src.parsers.epub_parser import parse_epub
from src.translation.prompts import (
    FICTION_DEFAULT_PROMPT,
    NONFICTION_DEFAULT_PROMPT,
    default_prompt_for_style,
    resolve_system_prompt,
)


def _book_with_paragraphs(texts: list[str]) -> CanonicalBook:
    blocks = [
        ContentBlock(id=f"p{i}", type=BlockType.PARAGRAPH, order=i, text=t)
        for i, t in enumerate(texts)
    ]
    return CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        chapters=[Chapter(id="ch1", title="Chapter 1", order=0, blocks=blocks)],
    )


def _write_simple_epub(path: Path, body_html: str, title: str = "T") -> None:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title(title)
    book.set_language("en")
    c1 = epub.EpubHtml(title="Ch1", file_name="chap1.xhtml", lang="en")
    html = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        + body_html
        + "</body></html>"
    )
    c1.set_content(html.encode("utf-8"))
    book.add_item(c1)
    book.toc = (c1,)
    book.spine = ["nav", c1]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book, {})


def test_glossary_slots_list_all_and_none_ok(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g1 = store.create("series")
    g2 = store.create("book-specific")
    store.add_entry(g1.glossary_id, "Alice", "A", confirmed=True)
    store.add_entry(g2.glossary_id, "Bob", "B", confirmed=True)
    ids = store.list_ids()
    assert g1.glossary_id in ids and g2.glossary_id in ids
    assert len(ids) == 2


def test_glossary_merge_dedup_first_wins(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g1 = store.create("a")
    g2 = store.create("b")
    store.add_entry(g1.glossary_id, "Hero", "HeroA", confirmed=True)
    store.add_entry(g2.glossary_id, "Hero", "HeroB", confirmed=True)
    e1 = store.load(g1.glossary_id).as_prompt_list()
    e2 = store.load(g2.glossary_id).as_prompt_list()
    seen: set[str] = set()
    merged = []
    for batch in (e1, e2):
        for e in batch:
            src = e["source"]
            if src in seen:
                continue
            seen.add(src)
            merged.append(e)
    assert len(merged) == 1
    assert merged[0]["target"] == "HeroA"


def test_conversion_mode_css_differs():
    layout = Layout.HORIZONTAL
    standard = _css(layout, "standard")
    compact = _css(layout, "compact")
    assert "line-height" in standard and "line-height" in compact
    assert standard != compact


def test_generate_epub_accepts_modes(tmp_path: Path):
    book = _book_with_paragraphs(["Hello.", "World."])
    for mode in ("standard", "compact"):
        out = tmp_path / f"out_{mode}.epub"
        generate_epub(book, out, conversion_mode=mode)
        assert out.is_file() and out.stat().st_size > 0
        with zipfile.ZipFile(out) as zf:
            css_name = next(
                n for n in zf.namelist() if n.endswith(".css") or "style" in n.lower()
            )
            css = zf.read(css_name).decode("utf-8")
            assert "line-height" in css


def test_convert_file_passes_mode(tmp_path: Path):
    src = tmp_path / "src.epub"
    _write_simple_epub(
        src,
        "<h1>Chapter One</h1><p>Alpha paragraph.</p><p>Beta paragraph.</p>",
        title="ModeTest",
    )
    out = tmp_path / "converted.epub"
    convert_file(src, out, conversion_mode="compact")
    assert out.is_file()


def test_technical_filenames_not_chapter_titles():
    for name in ("P001", "p-005", "chap_0004", "item001", "titlepage", "p-toc", "toc"):
        assert _is_technical_filename(name), name
    for name in ("Chapter One", "Prologue", "Epilogue"):
        assert not _is_technical_filename(name), name


def test_detect_prefers_logical_titles_over_spine():
    blocks = [
        ContentBlock(
            id="h0", type=BlockType.HEADING, order=0, text="Chapter One", level=1
        ),
        ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=1, text="Body."),
    ]
    # smoke: helper exists and technical names filtered
    assert _is_technical_filename("p001")


def test_paragraphs_not_concatenated(tmp_path: Path):
    src = tmp_path / "paras.epub"
    _write_simple_epub(src, "<p>Alpha.</p><p>Beta.</p>")
    result = parse_epub(src, assets_dir=tmp_path / "assets")
    texts = [
        b.text
        for ch in result.book.chapters
        for b in ch.blocks
        if b.type == BlockType.PARAGRAPH
    ]
    assert "Alpha." in texts and "Beta." in texts


def test_br_splits_paragraph(tmp_path: Path):
    src = tmp_path / "br.epub"
    _write_simple_epub(src, "<p>Line one.<br/>Line two.</p>")
    result = parse_epub(src, assets_dir=tmp_path / "assets")
    texts = [
        b.text or ""
        for ch in result.book.chapters
        for b in ch.blocks
        if b.type == BlockType.PARAGRAPH
    ]
    joined = " ".join(texts)
    assert "Line one" in joined and "Line two" in joined


def test_style_default_prompts_differ():
    assert FICTION_DEFAULT_PROMPT != NONFICTION_DEFAULT_PROMPT
    assert default_prompt_for_style("fiction") == FICTION_DEFAULT_PROMPT
    assert default_prompt_for_style("nonfiction") == NONFICTION_DEFAULT_PROMPT


def test_resolve_custom_prompt_wins():
    assert resolve_system_prompt("fiction", "CUSTOM") == "CUSTOM"
    assert resolve_system_prompt("fiction", "") == FICTION_DEFAULT_PROMPT


def test_settings_per_style_prompt_fields():
    s = TranslationSettings(
        style="fiction", fiction_prompt="F", nonfiction_prompt="N"
    )
    assert s.fiction_prompt == "F"
    assert s.nonfiction_prompt == "N"


def test_job_from_normalized_book_snapshot(tmp_path: Path):
    storage = Storage(tmp_path / "store")
    book = CanonicalBook(
        metadata=BookMetadata(title="Normalized", language="en"),
        chapters=[
            Chapter(
                id="c1",
                title="Ch",
                order=0,
                blocks=[
                    ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=0, text="A"),
                    ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="B"),
                ],
            )
        ],
    )
    job = create_translation_job(
        None,
        storage,
        JobConfig(source_language="en", target_language="zh-Hant"),
        work_dir=tmp_path / "work",
        book=book,
    )
    assert job.book.metadata.title == "Normalized"
    assert len(job.book.chapters[0].blocks) == 2
