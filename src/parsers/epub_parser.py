"""EPUB parser — thin wrapper; see chapter_detect for detection."""
from __future__ import annotations

import warnings
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
import ebooklib
from ebooklib import epub

from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.base import ParseResult
from src.parsers.chapter_detect import (
    _assign_chapters,
    _extract_nav_labels,
    _extract_toc_href_map,
    _guess_title,
    _is_technical_filename,
    _looks_like_chapter_title,
    _title_from_blocks,
    _toc_title_for_item,
    detect_chapters,
)
from src.utils.images import resize_book_assets

__all__ = [
    "parse_epub",
    "detect_chapters",
    "_assign_chapters",
    "_guess_title",
    "_is_technical_filename",
    "_looks_like_chapter_title",
    "_title_from_blocks",
]

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


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


def parse_epub(path: str | Path, assets_dir: Path | None = None) -> ParseResult:
    path = Path(path)
    book = epub.read_epub(str(path))
    warnings_list: list[str] = []

    meta = _extract_metadata(book)
    cover_ref, assets = _extract_images(book, assets_dir or path.parent / "_assets")
    assets = resize_book_assets(assets)

    toc_by_href = _extract_toc_href_map(book)
    toc_labels = list(dict.fromkeys(toc_by_href.values()))
    flat_blocks: list[ContentBlock] = []
    block_counter = 0
    spine_soft: list[tuple[int, str]] = []

    for item in _iter_spine_documents(book):
        try:
            html = item.get_content().decode("utf-8", errors="replace")
        except Exception as e:
            warnings_list.append(f"Failed to decode {item.get_name()}: {e}")
            continue
        soup = BeautifulSoup(html, "lxml")
        body = soup.body or soup
        blocks: list[ContentBlock] = []
        _walk(body, blocks, assets, counter_start=block_counter)
        if not blocks:
            continue
        start_idx = len(flat_blocks)
        soft = _toc_title_for_item(item, toc_by_href)
        if soft:
            spine_soft.append((start_idx, soft))
        block_counter += len(blocks)
        flat_blocks.extend(blocks)

    chapters = detect_chapters(
        flat_blocks,
        toc_labels=toc_labels,
        spine_soft_boundaries=spine_soft,
    )
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
        warnings=warnings_list,
        chapter_suggestions=suggestions,
    )


def _iter_spine_documents(book: epub.EpubBook):
    id_map: dict[str, object] = {}
    for item in book.get_items():
        iid = getattr(item, "id", None) or getattr(item, "get_id", lambda: None)()
        if iid:
            id_map[str(iid)] = item
        name = item.get_name() if hasattr(item, "get_name") else None
        if name:
            id_map[name] = item
            id_map[Path(name).name] = item

    yielded = False
    spine = getattr(book, "spine", None) or []
    for entry in spine:
        idref = entry[0] if isinstance(entry, (list, tuple)) else entry
        if idref in ("nav", "ncx", "cover", "titlepage"):
            continue
        item = id_map.get(str(idref))
        if item is None:
            continue
        try:
            itype = item.get_type()
        except Exception:
            itype = None
        if itype is not None and itype != _ITEM_DOCUMENT:
            continue
        name = (item.get_name() or "").lower()
        if any(k in name for k in ("nav.xhtml", "toc.xhtml", "toc.ncx", "nav.ncx")):
            continue
        yielded = True
        yield item

    if not yielded:
        for item in book.get_items_of_type(_ITEM_DOCUMENT):
            name = (item.get_name() or "").lower()
            if any(k in name for k in ("nav", "toc.ncx")):
                continue
            yield item


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


def _extract_images(book: epub.EpubBook, assets_dir: Path) -> tuple[str | None, dict[str, str]]:
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


def _walk(node, blocks, assets, counter_start=0):
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
        blocks.append(ContentBlock(id=bid, type=BlockType.IMAGE, order=len(blocks), image_ref=ref, image_alt=alt or None))
        return

    if name in _HEADING_TAGS:
        text = node.get_text(" ", strip=True)
        if text:
            level = int(name[1])
            bid = f"h{counter_start + len(blocks)}"
            blocks.append(ContentBlock(id=bid, type=BlockType.HEADING, order=len(blocks), text=text, level=level))
        return

    if name in ("figcaption", "caption"):
        text = node.get_text(" ", strip=True)
        if text:
            bid = f"cap{counter_start + len(blocks)}"
            blocks.append(ContentBlock(id=bid, type=BlockType.CAPTION, order=len(blocks), text=text))
        return

    if name in _BLOCK_TAGS:
        nested = [c for c in node.children if isinstance(c, Tag) and (c.name or "").lower() in (_BLOCK_TAGS | _HEADING_TAGS | {"img", "br"})]
        if nested or node.find("img") or node.find("br"):
            _emit_split_blocks(node, blocks, assets, counter_start)
            return
        text = node.get_text(" ", strip=True)
        if text:
            bid = f"p{counter_start + len(blocks)}"
            blocks.append(ContentBlock(id=bid, type=BlockType.PARAGRAPH, order=len(blocks), text=text))
        return

    for child in node.children:
        _walk(child, blocks, assets, counter_start)


def _emit_split_blocks(node, blocks, assets, counter_start):
    buf = []

    def flush():
        text = " ".join(p.strip() for p in buf if p and p.strip()).strip()
        buf.clear()
        if not text:
            return
        bid = f"p{counter_start + len(blocks)}"
        blocks.append(ContentBlock(id=bid, type=BlockType.PARAGRAPH, order=len(blocks), text=text))

    for child in node.children:
        if isinstance(child, NavigableString):
            s = str(child)
            if s.strip():
                buf.append(s)
            continue
        if not isinstance(child, Tag):
            continue
        cname = (child.name or "").lower()
        if cname == "br":
            flush()
            continue
        if cname in _HEADING_TAGS or cname in ("img", "figcaption", "caption"):
            flush()
            _walk(child, blocks, assets, counter_start)
            continue
        if cname in _BLOCK_TAGS:
            flush()
            _walk(child, blocks, assets, counter_start)
            continue
        t = child.get_text(" ", strip=True)
        if t:
            buf.append(t)
    flush()
