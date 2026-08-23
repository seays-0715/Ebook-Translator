"""TXT → Canonical Book parser.

Rules (spec §7 / §7.1):
- Blank lines are paragraph boundaries; consecutive blanks collapse.
- "One sentence per line" heuristic: if many consecutive non-empty short lines
  without blank separators, merge them into one paragraph.
- No images (TXT has no image concept).
"""

from __future__ import annotations

import re
from pathlib import Path

from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.parsers.base import ParseResult

# Chapter title patterns (language-aware basics)
_CHAPTER_PATTERNS = [
    re.compile(r"^(第\s*[0-9一二三四五六七八九十百千零〇两兩]+\s*[章节回話话集部篇])", re.I),
    re.compile(r"^(Chapter\s+\d+)\b", re.I),
    re.compile(r"^(CHAPTER\s+[IVXLCDM]+)\b"),
    re.compile(r"^(第\s*\d+\s*話)", re.I),
    re.compile(r"^(\d+\s*[\.、]\s*\S+)"),
]


def parse_txt(
    path: str | Path,
    *,
    short_line_threshold: int = 40,
    merge_short_lines: bool = True,
    encoding: str | None = None,
) -> ParseResult:
    path = Path(path)
    text = _read_text(path, encoding)
    lines = text.splitlines()

    # Detect chapters by pattern
    chapter_starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for pat in _CHAPTER_PATTERNS:
            m = pat.match(stripped)
            if m:
                chapter_starts.append((i, stripped[:200]))
                break

    if not chapter_starts:
        # Whole file as one chapter
        blocks = _lines_to_blocks(lines, merge_short_lines, short_line_threshold)
        chapters = [
            Chapter(id="ch1", title=path.stem, order=0, blocks=blocks)
        ]
    else:
        chapters = []
        for idx, (start, title) in enumerate(chapter_starts):
            end = (
                chapter_starts[idx + 1][0]
                if idx + 1 < len(chapter_starts)
                else len(lines)
            )
            # Skip the title line itself for body; title is chapter title
            body_lines = lines[start + 1 : end]
            blocks = _lines_to_blocks(
                body_lines, merge_short_lines, short_line_threshold
            )
            chapters.append(
                Chapter(
                    id=f"ch{idx + 1}",
                    title=title,
                    order=idx,
                    blocks=blocks,
                )
            )

    meta = BookMetadata(title=path.stem, author="Unknown", language="und")
    book = CanonicalBook(
        metadata=meta,
        layout=Layout.HORIZONTAL,
        chapters=chapters,
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
    return ParseResult(
        book=book,
        source_path=path,
        chapter_suggestions=suggestions,
    )


def _read_text(path: Path, encoding: str | None) -> str:
    if encoding:
        return path.read_text(encoding=encoding, errors="replace")
    for enc in ("utf-8", "utf-8-sig", "gbk", "big5", "shift_jis", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _lines_to_blocks(
    lines: list[str],
    merge_short: bool,
    threshold: int,
) -> list[ContentBlock]:
    """Convert lines to paragraph blocks with short-line merge heuristic."""
    blocks: list[ContentBlock] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip() if not merge_short else " ".join(buf).strip()
        if text:
            bid = f"p{len(blocks)}"
            blocks.append(
                ContentBlock(
                    id=bid,
                    type=BlockType.PARAGRAPH,
                    order=len(blocks),
                    text=text,
                )
            )
        buf = []

    consecutive_short = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            consecutive_short = 0
            continue

        is_short = len(stripped) < threshold
        if merge_short and is_short:
            buf.append(stripped)
            consecutive_short += 1
        else:
            if consecutive_short > 0 and buf:
                # End of short-line run
                flush()
            buf.append(stripped)
            if not is_short:
                flush()
            consecutive_short = 0 if not is_short else consecutive_short + 1

    flush()
    # Re-number order
    return [b.model_copy(update={"order": i}) for i, b in enumerate(blocks)]
