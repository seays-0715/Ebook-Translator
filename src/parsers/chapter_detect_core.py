"""Chapter Detection helpers for EPUB/TXT parsers.

Spine != chapter. Logical titles only. TOC is soft signal only.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from src.models.blocks import BlockType, ContentBlock
from src.models.book import Chapter

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
    r"index[-_]?\d*|"
    # front-matter / structural resource labels (not user chapter titles)
    r"title[-_]?page|"
    r"p[-_]?titlepage|"
    r"p[-_]?fmatter|"
    r"p[-_]?toc|"
    r"toc|"
    r"nav|"
    r"cover|"
    r"colophon|"
    r"copyright"
    r")$",
    re.IGNORECASE,
)

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
    """True when text is a semantic chapter title (not body, not technical id)."""
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
    for b in blocks:
        title = _title_from_block(b)
        if title:
            return title
    return None


def _guess_title(soup: BeautifulSoup, fallback: str) -> str | None:
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


def _normalize_href(href: str | None) -> str:
    if not href:
        return ""
    h = str(href).split("#")[0].strip()
    return Path(h).name.lower()


def _extract_toc_href_map(book: epub.EpubBook) -> dict[str, str]:
    mapping: dict[str, str] = {}

    def add(title: str | None, href: str | None) -> None:
        if not title:
            return
        t = str(title).strip()
        if not t or _is_technical_filename(t) or len(t) > _MAX_TITLE_LEN:
            return
        key = _normalize_href(href)
        if key and key not in mapping:
            mapping[key] = t[:200]

    def walk(entry) -> None:
        if entry is None:
            return
        if isinstance(entry, (list, tuple)):
            for e in entry:
                walk(e)
            return
        title = getattr(entry, "title", None)
        href = getattr(entry, "href", None) or getattr(entry, "file_name", None)
        add(title, href)
        for child in getattr(entry, "children", None) or []:
            walk(child)

    try:
        walk(getattr(book, "toc", None) or ())
    except Exception:
        pass

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
                add(a.get_text(" ", strip=True), a.get("href"))
            for np in soup.find_all("navPoint"):
                label_el = np.find("navLabel")
                content_el = np.find("content")
                t = label_el.get_text(" ", strip=True) if label_el else ""
                href = content_el.get("src") if content_el else None
                add(t, href)
    except Exception:
        pass

    return mapping


def _toc_title_for_item(item, toc_by_href: dict[str, str]) -> str | None:
    if not toc_by_href:
        return None
    name = ""
    if hasattr(item, "get_name"):
        name = item.get_name() or ""
    key = _normalize_href(name)
    if key and key in toc_by_href:
        return toc_by_href[key]
    iid = getattr(item, "id", None)
    if iid and str(iid).lower() in toc_by_href:
        return toc_by_href[str(iid).lower()]
    return None


def _extract_nav_labels(book: epub.EpubBook) -> list[str]:
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
