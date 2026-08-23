"""EPUB → Canonical Book parser.

Strips publisher CSS / decoration. Keeps reading-order Content Blocks
(paragraph, image, caption, heading, footnote). Cover and body images retained.

Spine items are initial chapter candidates only — not permanent semantic source
of truth. Chapter Detection / Preview / User Correction is authoritative.
Original EPUB TOC/NCX/Nav is never used as Canonical Book structure.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup, NavigableString, Tag
import ebooklib
from ebooklib import epub

from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.base import ParseResult
from src.utils.images import resize_book_assets

# ebooklib 0.17+ exposes ITEM_* on the top-level package, not ebooklib.epub.
def _item_type(name: str, default: int | None = None) -> int:
    for mod in (ebooklib, epub):
        val = getattr(mod, name, None)
        if val is not None:
            return int(val)
    if default is not None:
        return default
    raise AttributeError(f"ebooklib has no attribute {name!r}")


_ITEM_DOCUMENT = _item_type("ITEM_DOCUMENT", 9)
_ITEM_IMAGE = _item_type("ITEM_IMAGE", 1)
_ITEM_COVER = _item_type("ITEM_COVER", 10)

_BLOCK_TAGS = {
    "p", "div", "section", "article", "blockquote", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "figcaption", "caption", "td", "th", "dt", "dd", "pre",
}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "nav", "aside", "header", "footer", "iframe"}

_TECH_NAME_RE = re.compile(
    r"^(?:"
    r"p\d+|"
    r"item\d+|"
    r"sec(?:tion)?\d+|"
    r"chap(?:ter)?_?\d+|"
    r"part\d+|"
    r"page_?\d+|"
    r"xhtml?\d+|"
    r"text/?\d+|"
    r"content\d+|"
    r"doc(?:ument)?\d+|"
    r"OEBPS.*|"
    r"index_?\d*"
    r")$",
    re.IGNORECASE,
)
_CHAPTER_TITLE_RE = re.compile(
    r"^("
    r"第\s*[0-9零一二三四五六七八九十百千两兩〇]+\s*[章节節回卷部篇]"
    r"|chapter\s+\d+"
    r"|ch\.?\s*\d+"
    r"|part\s+\d+"
    r"|prologue|epilogue|前言|序章|序|後記|后记|跋|楔子|終章|终章"
    r")\b",
    re.IGNORECASE,
)


def _is_technical_filename(name: str) -> bool:
    stem = Path(name).stem.strip()
    if not stem:
        return True
    if _TECH_NAME_RE.match(stem):
        return True
    if re.fullmatch(r"[A-Za-z]?\d{2,6}", stem):
        return True
    return False


def _title_from_blocks(blocks: list[ContentBlock]) -> str | None:
    for b in blocks:
        if b.type == BlockType.HEADING and (b.text or "").strip():
            t = b.text.strip()
            if not _is_technical_filename(t):
                return t[:200]
    for b in blocks[:5]:
        if b.type == BlockType.PARAGRAPH and (b.text or "").strip():
            t = b.text.strip()
            if len(t) <= 80 and _CHAPTER_TITLE_RE.match(t):
                return t[:200]
    return None


def parse_epub(path: str | Path, assets_dir: Path | None = None) -> ParseResult:
    path = Path(path)
    book = epub.read_epub(str(path))
    warnings: list[str] = []

    meta = _extract_metadata(book)
    cover_ref, assets = _extract_images(book, assets_dir or path.parent / "_assets")
    assets = resize_book_assets(assets)
    spine_items = list(book.get_items_of_type(_ITEM_DOCUMENT))

    raw_chapters: list[tuple[str | None, list[ContentBlock]]] = []
    block_counter = 0

    for item in spine_items:
        try:
            html = item.get_content().decode("utf-8", errors="replace")
        except Exception as e:
            warnings.append(f"Failed to decode {item.get_name()}: {e}")
            continue
        soup = BeautifulSoup(html, "lxml")
        body = soup.body or soup
        blocks: list[ContentBlock] = []
        _walk(body, blocks, assets, counter_start=block_counter)
        block_counter += len(blocks)
        title = _guess_title(soup, item.get_name())
        if blocks:
            raw_chapters.append((title, blocks))

    chapters = _assign_chapters(raw_chapters)
    suggestions = [
        {"id": ch.id, "title": ch.title, "order": ch.order, "block_count": len(ch.blocks)}
        for ch in chapters
    ]

    canon = CanonicalBook(
        metadata=meta,
        cover_ref=cover_ref,
        layout=Layout.HORIZONTAL,
        chapters=chapters,
        assets=assets,
    )
    return ParseResult(
        book=canon,
        source_path=path,
        warnings=warnings,
        chapter_suggestions=suggestions,
    )


def _extract_metadata(book: epub.EpubBook) -> BookMetadata:
    def first(name: str) -> str | None:
        vals = book.get_metadata("DC", name)
        if vals:
            return str(vals[0][0])
        return None

    return BookMetadata(
        title=first("title") or "Untitled",
        author=first("creator") or "Unknown",
        language=first("language") or "und",
        identifier=first("identifier"),
        publisher=first("publisher"),
        description=first("description"),
    )


def _extract_images(
    book: epub.EpubBook, assets_dir: Path
) -> tuple[str | None, dict[str, str]]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}
    cover_ref: str | None = None

    for item in book.get_items():
        itype = item.get_type()
        is_cover = itype == _ITEM_COVER or (
            hasattr(item, "id") and item.id and "cover" in str(item.id).lower()
        )
        if is_cover and itype in (_ITEM_IMAGE, _ITEM_COVER):
            key = f"cover_{uuid4().hex[:8]}"
            ext = Path(item.get_name()).suffix or ".jpg"
            rel = f"{key}{ext}"
            out = assets_dir / rel
            out.write_bytes(item.get_content())
            assets[key] = str(out)
            cover_ref = key
            break

    for item in book.get_items_of_type(_ITEM_IMAGE):
        name = item.get_name()
        key = f"img_{uuid4().hex[:8]}"
        ext = Path(name).suffix or ".jpg"
        rel = f"{key}{ext}"
        out = assets_dir / rel
        out.write_bytes(item.get_content())
        assets[name] = str(out)
        assets[key] = str(out)

    return cover_ref, assets


def _walk(
    node: Tag | NavigableString,
    blocks: list[ContentBlock],
    assets: dict[str, str],
    counter_start: int = 0,
) -> None:
    if isinstance(node, NavigableString):
        return
    if not isinstance(node, Tag):
        return
    name = node.name.lower() if node.name else ""
    if name in _SKIP_TAGS:
        return

    if name == "img":
        src = node.get("src") or node.get("data-src") or ""
        alt = node.get("alt") or ""
        ref = None
        base = Path(src).name
        for k, v in assets.items():
            if base and (base in k or base in v or k.endswith(base)):
                ref = k
                break
        if ref is None and src:
            ref = src
        bid = f"img{counter_start + len(blocks)}"
        blocks.append(
            ContentBlock(
                id=bid, type=BlockType.IMAGE, order=len(blocks),
                image_ref=ref, image_alt=alt or None,
            )
        )
        return

    if name in _HEADING_TAGS:
        text = node.get_text(" ", strip=True)
        if text:
            level = int(name[1])
            bid = f"h{counter_start + len(blocks)}"
            blocks.append(
                ContentBlock(
                    id=bid, type=BlockType.HEADING, order=len(blocks),
                    text=text, level=level,
                )
            )
        return

    if name in ("figcaption", "caption"):
        text = node.get_text(" ", strip=True)
        if text:
            bid = f"cap{counter_start + len(blocks)}"
            blocks.append(
                ContentBlock(
                    id=bid, type=BlockType.CAPTION, order=len(blocks), text=text,
                )
            )
        return

    if name in _BLOCK_TAGS:
        has_img = node.find("img") is not None
        if has_img:
            for child in node.children:
                _walk(child, blocks, assets, counter_start)
            return
        text = node.get_text(" ", strip=True)
        if text:
            bid = f"p{counter_start + len(blocks)}"
            blocks.append(
                ContentBlock(
                    id=bid, type=BlockType.PARAGRAPH, order=len(blocks), text=text,
                )
            )
        return

    for child in node.children:
        _walk(child, blocks, assets, counter_start)


def _guess_title(soup: BeautifulSoup, fallback: str) -> str | None:
    """Structural title from HTML. Never returns technical filenames."""
    for tag in ("h1", "h2", "h3", "title"):
        el = soup.find(tag)
        if el:
            t = el.get_text(" ", strip=True)
            if t and not _is_technical_filename(t):
                if _is_technical_filename(fallback) and t.lower() == Path(fallback).stem.lower():
                    continue
                return t[:200]
    if fallback and not _is_technical_filename(fallback):
        stem = Path(fallback).stem.strip()
        if stem and not _is_technical_filename(stem):
            return stem[:200]
    return None


def _assign_chapters(
    raw: list[tuple[str | None, list[ContentBlock]]],
) -> list[Chapter]:
    """Initial grouping: spine preserves reading order; titles from structure."""
    chapters: list[Chapter] = []
    for i, (title, blocks) in enumerate(raw):
        fixed = [b.model_copy(update={"order": j}) for j, b in enumerate(blocks)]
        from_blocks = _title_from_blocks(fixed)
        final_title = from_blocks or title
        if not final_title or _is_technical_filename(final_title):
            final_title = f"Chapter {i + 1}"
        chapters.append(
            Chapter(
                id=f"ch{i + 1}",
                title=final_title,
                order=i,
                blocks=fixed,
            )
        )
    return chapters
