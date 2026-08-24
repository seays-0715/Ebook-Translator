"""Chapter Detection — public API."""
from __future__ import annotations

from src.models.blocks import ContentBlock
from src.models.book import Chapter
from src.parsers.chapter_detect_core import (
    _MAX_TITLE_LEN,
    _is_technical_filename,
    _title_from_block,
    _title_from_blocks,
    _looks_like_chapter_title,
    _guess_title,
    _extract_toc_href_map,
    _toc_title_for_item,
    _extract_nav_labels,
    _collect_toc_labels,
    _normalize_href,
)

__all__ = [
    "detect_chapters",
    "_assign_chapters",
    "_is_technical_filename",
    "_looks_like_chapter_title",
    "_title_from_blocks",
    "_guess_title",
    "_extract_toc_href_map",
    "_toc_title_for_item",
    "_extract_nav_labels",
]


def detect_chapters(
    flat_blocks: list[ContentBlock],
    *,
    toc_labels: list[str] | None = None,
    spine_soft_boundaries: list[tuple[int, str]] | None = None,
) -> list[Chapter]:
    if not flat_blocks:
        return []

    toc_list = [t.strip() for t in (toc_labels or []) if t and t.strip()]
    toc_set = set(toc_list)

    spine_title_at: dict[int, str] = {}
    for idx, title in spine_soft_boundaries or []:
        if 0 <= idx < len(flat_blocks) and title and not _is_technical_filename(title):
            spine_title_at[idx] = title[:200]

    boundaries: list[tuple[int, str]] = []

    def _add_boundary(i: int, title: str) -> None:
        if boundaries and boundaries[-1][1] == title and boundaries[-1][0] == i - 1:
            return
        if boundaries and boundaries[-1][0] == i:
            return
        boundaries.append((i, title))

    for i, b in enumerate(flat_blocks):
        title = _title_from_block(b)
        if title is None and toc_set:
            t = (b.text or "").strip()
            if t and not _is_technical_filename(t):
                if t in toc_set:
                    title = t[:200]
                else:
                    for lab in toc_list:
                        if t.startswith(lab) or lab.startswith(t):
                            if min(len(t), len(lab)) >= 2:
                                title = lab[:200]
                                break
        if title is not None:
            _add_boundary(i, title)

    if not boundaries and spine_title_at:
        for idx in sorted(spine_title_at):
            _add_boundary(idx, spine_title_at[idx])

    if not boundaries:
        title = _title_from_blocks(flat_blocks) or "Untitled"
        if _is_technical_filename(title):
            title = "Untitled"
        if title == "Untitled" and toc_list:
            for lab in toc_list:
                if not _is_technical_filename(lab):
                    title = lab[:200]
                    break
        fixed = [b.model_copy(update={"order": j}) for j, b in enumerate(flat_blocks)]
        return [Chapter(id="ch1", title=title, order=0, blocks=fixed)]

    chapters: list[Chapter] = []
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
    flat: list[ContentBlock] = []
    for _title, blocks in raw:
        flat.extend(blocks)
    return detect_chapters(flat)
