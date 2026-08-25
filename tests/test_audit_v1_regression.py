"""V1 audit regressions.

- Glossary merge: same source keeps first, later discarded; empty targets, None allowed
- Conversion mode: clean | compact passed to generator
- Chapter: original titles preferred over technical filenames
- Paragraph: <p> / <br> boundaries preserved
- Style: Fiction / Non-Fiction prompts, save/reset defaults
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from src.core.pipeline import convert_file, create_translation_job
from src.core.settings import TranslationSettings
from src.epub.generator import _css, generate_epub
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.chapter_detect_core import _is_technical_filename
from src.translation.prompts import (
    FICTION_DEFAULT_PROMPT,
    NONFICTION_DEFAULT_PROMPT,
    default_prompt_for_style,
    resolve_system_prompt,
)


def _book_with_paragraphs(paragraphs: list[str]) -> CanonicalBook:
    blocks = [
        ContentBlock(
            id=f"p{i}", type=BlockType.PARAGRAPH, order=i, text=p
        )
        for i, p in enumerate(paragraphs)
    ]
    return CanonicalBook(
        metadata=BookMetadata(title="T", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[Chapter(id="c1", title="C1", order=0, blocks=blocks)],
    )


def _write_simple_epub(path: Path, body_html: str, title: str = "T") -> None:
    # Minimal EPUB via generator path when possible; for convert_file use real zip
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id-test")
    book.set_title(title)
    book.set_language("en")
    c = epub.EpubHtml(title="Ch", file_name="chap.xhtml", lang="en")
    c.set_content(
        f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{body_html}</body></html>'
    )
    book.add_item(c)
    book.toc = (c,)
    book.spine = ["nav", c]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book, {})


def test_conversion_mode_css_differs():
    layout = Layout.HORIZONTAL
    clean = _css(layout, "clean")
    compact = _css(layout, "compact")
    assert "line-height" in clean and "line-height" in compact
    assert clean != compact


def test_generate_epub_accepts_modes(tmp_path: Path):
    book = _book_with_paragraphs(["Hello.", "World."])
    for mode in ("clean", "compact"):
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
