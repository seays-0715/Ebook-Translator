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
    r"第\s*[0-9０-９零一二三四五六七八九十百千两兩〇壹貳參叄肆伍陸柒捌玖拾]+\s*[章节節回卷部篇話话]"
    r"|第\s*\d+\s*[章节節回卷部篇話话]"
    r"|chapter\s+\d+"
    r"|ch\.?\s*\d+"
    r"|part\s+\d+"
    r"|prologue|epilogue"
    r"|前言|序章|序[章言]?|後記|后记|跋|楔子|終章|终章|尾聲|尾声"
    r"|幕間|幕间"
    r"|追加\s*SS|番外|特典|特別篇|特别篇"
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
    # TOC href → label is a soft signal for document-start boundaries only.
    toc_by_href = _extract_toc_href_map(book)
    toc_labels = list(dict.fromkeys(toc_by_href.values()))  # ordered unique labels
    flat_blocks: list[ContentBlock] = []
    block_counter = 0
    # (block_index, soft_title) for spine-document starts that TOC points to
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
        # Soft title from TOC if this document is a TOC target
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
