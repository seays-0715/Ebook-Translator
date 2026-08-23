"""EPUB → Canonical Book parser.

Strips publisher CSS / decoration. Keeps reading-order Content Blocks
(paragraph, image, caption, heading, footnote). Cover and body images retained.

Spine items are document/resource boundaries ONLY — never logical chapters.
Chapter structure comes solely from Chapter Detection (headings / structural
patterns / optional TOC soft-signal), then user confirmation in Preview.
Normalized TOC is always regenerated from the confirmed Canonical Book chapters.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
import ebooklib
from ebooklib import epub

from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.base import ParseResult
from src.utils.images import resize_book_assets

# Suppress XML-as-HTML noise from publisher XHTML; content is still extracted.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ebooklib 0.17+ exposes ITEM_* on the top-level package, not ebooklib.epub.
# Support both layouts for frozen EXE / pip version variance.
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

# Tags treated as block-level content
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "blockquote",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "figcaption",
    "caption",
    "td",
    "th",
    "dt",
    "dd",
    "pre",
}

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "nav", "aside", "header", "footer", "iframe"}

# Technical spine / page labels that must never become user-facing titles
_TECH_NAME_RE = re.compile(
    r"^(?:"
    r"p[-_]?\d+|"               # P001, p12, p-005, p_006
    r"item[-_]?\d+|"            # item001, item-12
    r"sec(?:tion)?[-_]?\d+|"    # sec01, section1
    r"chap(?:ter)?[-_]?\d+|"    # chap_1, chapter01, chap-0004, chap_0004
    r"part[-_]?\d+|"
    r"page[-_]?\d+|"
    r"xhtml?[-_]?\d+|"
    r"text[-_/]?\d+|"
    r"content[-_]?\d+|"
    r"doc(?:ument)?[-_]?\d+|"
    r"OEBPS.*|"
    r"index[-_]?\d*"
    r")$",
    re.IGNORECASE,
)

# Semantic chapter title patterns (language-aware, V1)
# Matches start of title line; rest of title (e.g. after full-width space) is kept.
_CHAPTER_TITLE_RE = re.compile(
    r"^("
    r"第\s*[0-9零一二三四五六七八九十百千两兩〇]+\s*[章节節回卷部篇話话]"  # 第一章 / 第一話
    r"|第\s*\d+\s*[章节節回卷部篇話话]"
    r"|chapter\s+\d+"
    r"|ch\.?\s*\d+"
    r"|part\s+\d+"
    r"|prologue|epilogue"
    r"|前言|序章|序[章言]?|後記|后记|跋|楔子|終章|终章|尾聲|尾声"
    r"|幕間|幕间"
    r"|追加\s*SS|番外|特典"
    r")",
    re.IGNORECASE,
)

_MAX_TITLE_LEN = 80


def parse_epub(path: str | Path, assets_dir: Path | None = None) -> ParseResult:
    path = Path(path)
    book = epub.read_epub(str(path))
    warnings_list: list[str] = []

    meta = _extract_metadata(book)
    cover_ref, assets = _extract_images(book, assets_dir or path.parent / "_assets")
    assets = resize_book_assets(assets)

    # Spine = document/resource boundaries only. Flatten into reading-order blocks.
    # Chapter Detection (not spine) produces logical Chapter structure.
    flat_blocks: list[ContentBlock] = []
    block_counter = 0

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
        block_counter += len(blocks)
        flat_blocks.extend(blocks)

    # Optional soft signal: Nav/TOC labels (never copied as final TOC)
    toc_labels = _extract_nav_labels(book)
    chapters = detect_chapters(flat_blocks, toc_labels=toc_labels)
    suggestions = [
        {
            "id": ch.id,
            "title": ch.title,
            "order": ch.order,
            "block_count": len(ch.blocks),
        }
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
    """Yield document items in true spine reading order.

    Falls back to get_items_of_type when spine is empty/missing.
    Skips nav/ncx-only items that are not linear content.
    """
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
        if isinstance(entry, (list, tuple)):
            idref = entry[0]
        else:
            idref = entry
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
                id=bid,
                type=BlockType.IMAGE,
                order=len(blocks),
                image_ref=ref,
                image_alt=alt or None,
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
                    id=bid,
                    type=BlockType.HEADING,
                    order=len(blocks),
                    text=text,
                    level=level,
                )
            )
        return

    if name in ("figcaption", "caption"):
        text = node.get_text(" ", strip=True)
        if text:
            bid = f"cap{counter_start + len(blocks)}"
            blocks.append(
                ContentBlock(
                    id=bid,
                    type=BlockType.CAPTION,
                    order=len(blocks),
                    text=text,
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
                    id=bid,
                    type=BlockType.PARAGRAPH,
                    order=len(blocks),
                    text=text,
                )
            )
        return

    for child in node.children:
        _walk(child, blocks, assets, counter_start)


def _is_technical_filename(name: str) -> bool:
    """True if name looks like a spine/XHTML/page technical id, not a title."""
    stem = Path(str(name)).stem.strip()
    if not stem:
        return True
    if _TECH_NAME_RE.match(stem):
        return True
    if re.fullmatch(r"[A-Za-z]?\d{2,6}", stem):
        return True
    if re.fullmatch(r"[A-Za-z]{0,8}[-_]\d{1,6}", stem):
        return True
    return False


def _looks_like_chapter_title(text: str) -> bool:
    """True when text is a semantic chapter title (not body, not technical id).

    Requires a clear boundary after the marker so body lines like
    「第一話正文續頁」 or 「幕間正文」 are not treated as titles.
    Allowed: pure marker (尾聲), or marker + separator + subtitle
    (第一話　試著把…).
    """
    t = (text or "").strip()
    if not t or len(t) > _MAX_TITLE_LEN:
        return False
    if _is_technical_filename(t):
        return False
    m = _CHAPTER_TITLE_RE.match(t)
    if not m:
        return False
    rest = t[m.end() :]
    if not rest:
        return True
    if rest[0] in " \t　 :：—－–-·・|｜/／":
        return True
    return False


def _title_from_block(block: ContentBlock) -> str | None:
    """Return chapter title if this block is a chapter boundary marker."""
    t = (block.text or "").strip()
    if not t or _is_technical_filename(t):
        return None
    if block.type == BlockType.HEADING:
        level = block.level or 2
        if level <= 1:
            return t[:200]
        if _looks_like_chapter_title(t) or (level == 2 and len(t) <= 40):
            return t[:200]
        return None
    if block.type == BlockType.PARAGRAPH and _looks_like_chapter_title(t):
        return t[:200]
    return None


def _title_from_blocks(blocks: list[ContentBlock]) -> str | None:
    """Prefer first chapter-boundary block title inside a block slice."""
    for b in blocks:
        title = _title_from_block(b)
        if title:
            return title
    return None


def _guess_title(soup: BeautifulSoup, fallback: str) -> str | None:
    """Structural title from HTML. Never returns technical filenames.

    Kept for tests / callers; Chapter Detection uses detect_chapters on flat blocks.
    """
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


def _extract_nav_labels(book: epub.EpubBook) -> list[str]:
    """Collect Nav/NCX labels as soft signals only (never final TOC)."""
    labels: list[str] = []
    try:
        for item in book.get_items():
            name = (item.get_name() or "").lower()
            props = getattr(item, "properties", None) or []
            is_nav = any(k in name for k in ("nav", "toc", "ncx")) or "nav" in props
            if not is_nav:
                continue
            try:
                html = item.get_content().decode("utf-8", errors="replace")
            except Exception:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a"):
                t = a.get_text(" ", strip=True)
                if t and not _is_technical_filename(t) and len(t) <= _MAX_TITLE_LEN:
                    labels.append(t[:200])
            for navpoint in soup.find_all(["navpoint", "navLabel", "text"]):
                t = navpoint.get_text(" ", strip=True)
                if t and not _is_technical_filename(t) and len(t) <= _MAX_TITLE_LEN:
                    labels.append(t[:200])
        toc = getattr(book, "toc", None) or ()
        for entry in toc:
            _collect_toc_labels(entry, labels)
    except Exception:
        pass
    seen: set[str] = set()
    out: list[str] = []
    for t in labels:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _collect_toc_labels(entry, labels: list[str]) -> None:
    """Recursively collect labels from ebooklib toc structure."""
    if entry is None:
        return
    if isinstance(entry, (list, tuple)):
        for e in entry:
            _collect_toc_labels(e, labels)
        return
    title = getattr(entry, "title", None)
    if title and isinstance(title, str):
        t = title.strip()
        if t and not _is_technical_filename(t) and len(t) <= _MAX_TITLE_LEN:
            labels.append(t[:200])
    for child in getattr(entry, "children", None) or []:
        _collect_toc_labels(child, labels)


def detect_chapters(
    flat_blocks: list[ContentBlock],
    *,
    toc_labels: list[str] | None = None,
) -> list[Chapter]:
    """Detect logical chapters from a reading-order block stream.

    Spine/document boundaries are intentionally ignored here: one spine item may
    contain multiple chapters, and one chapter may span multiple spine items.

    toc_labels: optional Nav/TOC strings used only as soft signals (match against
    block text). Never copied wholesale as the Canonical Book chapter list.
    """
    if not flat_blocks:
        return []

    toc_set = {t.strip() for t in (toc_labels or []) if t and t.strip()}

    boundaries: list[tuple[int, str]] = []
    for i, b in enumerate(flat_blocks):
        title = _title_from_block(b)
        if title is None and toc_set:
            t = (b.text or "").strip()
            if t in toc_set and not _is_technical_filename(t):
                title = t[:200]
        if title is not None:
            if boundaries and boundaries[-1][1] == title and boundaries[-1][0] == i - 1:
                continue
            boundaries.append((i, title))

    chapters: list[Chapter] = []

    if not boundaries:
        # No semantic markers — single logical chapter (not one-per-spine).
        title = _title_from_blocks(flat_blocks) or "Untitled"
        if _is_technical_filename(title):
            title = "Untitled"
        fixed = [b.model_copy(update={"order": j}) for j, b in enumerate(flat_blocks)]
        return [Chapter(id="ch1", title=title, order=0, blocks=fixed)]

    for bi, (start, title) in enumerate(boundaries):
        end = boundaries[bi + 1][0] if bi + 1 < len(boundaries) else len(flat_blocks)
        if bi == 0:
            slice_blocks = flat_blocks[0:end]
        else:
            slice_blocks = flat_blocks[start:end]
        if not slice_blocks:
            continue
        if _is_technical_filename(title):
            title = _title_from_blocks(slice_blocks) or "Untitled"
            if _is_technical_filename(title):
                title = "Untitled"
        fixed = [b.model_copy(update={"order": j}) for j, b in enumerate(slice_blocks)]
        chapters.append(
            Chapter(
                id=f"ch{len(chapters) + 1}",
                title=title,
                order=len(chapters),
                blocks=fixed,
            )
        )

    return chapters


def _assign_chapters(
    raw: list[tuple[str | None, list[ContentBlock]]],
) -> list[Chapter]:
    """Legacy helper: flatten spine slices then run logical Chapter Detection.

    Do **not** map each spine item to one Chapter. Kept for older tests that
    pass pre-sliced (title, blocks) pairs.
    """
    flat: list[ContentBlock] = []
    for _title, blocks in raw:
        flat.extend(blocks)
    return detect_chapters(flat)
