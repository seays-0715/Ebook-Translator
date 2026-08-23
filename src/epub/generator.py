"""Canonical Book → clean EPUB generator.

Atomic write: write to .tmp then rename after basic checks.
TOC always regenerated from Chapter structure (never from original NCX/Nav).
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from ebooklib import epub

from src.models.blocks import BlockType
from src.models.book import CanonicalBook, Layout


def generate_epub(
    book: CanonicalBook,
    output_path: str | Path,
    *,
    assets_base: Path | None = None,
) -> Path:
    """Generate EPUB. Returns final path. Uses atomic write."""
    output_path = Path(output_path)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    eb = epub.EpubBook()
    eb.set_identifier(book.metadata.identifier or f"id-{book.metadata.title}")
    eb.set_title(book.metadata.title)
    eb.set_language(book.metadata.language or "en")
    if book.metadata.author:
        eb.add_author(book.metadata.author)

    # Cover
    if book.cover_ref and book.assets.get(book.cover_ref):
        cover_path = Path(book.assets[book.cover_ref])
        if cover_path.exists():
            data = cover_path.read_bytes()
            eb.set_cover(cover_path.name, data)

    style = _css(book.layout)
    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=style.encode("utf-8"),
    )
    eb.add_item(nav_css)

    spine_items: list = []
    toc = []
    image_items: dict[str, epub.EpubItem] = {}

    # Register images
    for key, rel in book.assets.items():
        p = Path(rel)
        if not p.exists():
            continue
        if key == book.cover_ref:
            continue
        data = p.read_bytes()
        media = _guess_media(p.suffix)
        item = epub.EpubItem(
            uid=f"img_{key}",
            file_name=f"images/{p.name}",
            media_type=media,
            content=data,
        )
        eb.add_item(item)
        image_items[key] = item
        image_items[p.name] = item

    for ch in book.chapters:
        html_body = _chapter_html(ch, image_items)
        file_name = f"chap_{ch.order:04d}.xhtml"
        chapter = epub.EpubHtml(
            title=ch.title or f"Chapter {ch.order + 1}",
            file_name=file_name,
            lang=book.metadata.language or "en",
        )
        # ebooklib expects content as the inner body or full document;
        # set as HTML fragment with proper structure
        chapter.set_content(
            f"<html xmlns=\"http://www.w3.org/1999/xhtml\">"
            f"<head><title>{escape(ch.title or '')}</title>"
            f'<link rel="stylesheet" type="text/css" href="style/nav.css"/>'
            f"</head><body>{html_body}</body></html>"
        )
        chapter.add_item(nav_css)
        eb.add_item(chapter)
        spine_items.append(chapter)
        toc.append(chapter)

    if not spine_items:
        # Empty book guard
        empty = epub.EpubHtml(title="Empty", file_name="empty.xhtml", lang="en")
        empty.set_content(
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p></p></body></html>'
        )
        eb.add_item(empty)
        spine_items.append(empty)

    eb.toc = tuple(toc) if toc else ()
    eb.spine = ["nav"] + spine_items
    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: generate to .tmp, require non-empty, then rename
    epub.write_epub(str(tmp_path), eb, {})
    if not tmp_path.is_file() or tmp_path.stat().st_size == 0:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"EPUB generation produced empty file: {tmp_path}")
    tmp_path.replace(output_path)
    return output_path


def _chapter_html(chapter, image_items: dict) -> str:
    parts: list[str] = []
    parts.append(f"<h1>{escape(chapter.title or '')}</h1>")
    for b in chapter.blocks:
        if b.type == BlockType.HEADING:
            level = min(max(b.level or 2, 1), 6)
            parts.append(f"<h{level}>{escape(b.text or '')}</h{level}>")
        elif b.type == BlockType.PARAGRAPH:
            parts.append(f"<p>{escape(b.text or '')}</p>")
        elif b.type == BlockType.CAPTION:
            parts.append(f'<p class="caption">{escape(b.text or "")}</p>')
        elif b.type == BlockType.FOOTNOTE:
            parts.append(f'<p class="footnote">{escape(b.text or "")}</p>')
        elif b.type == BlockType.IMAGE:
            src = None
            if b.image_ref and b.image_ref in image_items:
                src = image_items[b.image_ref].file_name
            elif b.image_ref:
                from pathlib import Path as P

                base = P(b.image_ref).name
                if base in image_items:
                    src = image_items[base].file_name
            if src:
                alt = escape(b.image_alt or "")
                parts.append(f'<img src="{src}" alt="{alt}"/>')
    return "\n".join(parts)


def _css(layout: Layout) -> str:
    direction = "vertical-rl" if layout == Layout.VERTICAL else "horizontal-tb"
    return f"""
body {{
  font-family: serif;
  line-height: 1.6;
  margin: 1em;
  writing-mode: {direction};
}}
h1, h2, h3, h4, h5, h6 {{
  font-weight: bold;
  margin: 1em 0 0.5em;
}}
p {{
  margin: 0.6em 0;
  text-indent: 1.5em;
}}
p.caption {{
  text-indent: 0;
  font-size: 0.9em;
  color: #444;
  text-align: center;
}}
p.footnote {{
  text-indent: 0;
  font-size: 0.85em;
  color: #555;
}}
img {{
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1em auto;
}}
"""


def _guess_media(suffix: str) -> str:
    s = suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(s, "application/octet-stream")
