"""Generated EPUB must include readable default typography."""

from __future__ import annotations

import zipfile
from pathlib import Path

from src.epub.generator import generate_epub
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout


def test_css_has_spacing_defaults(tmp_path: Path):
    book = CanonicalBook(
        metadata=BookMetadata(title="T", author="A", language="en"),
        layout=Layout.HORIZONTAL,
        chapters=[
            Chapter(
                id="ch1",
                title="第一章",
                order=0,
                blocks=[
                    ContentBlock(
                        id="p0", type=BlockType.PARAGRAPH, order=0, text="Hello."
                    ),
                    ContentBlock(
                        id="p1", type=BlockType.PARAGRAPH, order=1, text="World."
                    ),
                ],
            )
        ],
        assets={},
    )
    out = tmp_path / "out.epub"
    generate_epub(book, out)
    assert out.is_file()

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        css_name = next(n for n in names if n.endswith(".css") or "style" in n.lower())
        css = zf.read(css_name).decode("utf-8")
        assert "line-height" in css
        assert "margin" in css
        xhtml = next(n for n in names if n.endswith(".xhtml") and "chap" in n)
        body = zf.read(xhtml).decode("utf-8")
        assert "第一章" in body
        assert "Hello." in body
