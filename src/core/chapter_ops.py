"""Chapter Preview operations (spec §3.1).

V1 scope:
- Merge adjacent chapters only
- Split a single chapter into two at a block boundary
- Rename / Remove
No arbitrary cross-chapter block moves.
"""

from __future__ import annotations

from src.models.blocks import ContentBlock
from src.models.book import CanonicalBook, Chapter


class ChapterOpError(ValueError):
    pass


def rename_chapter(book: CanonicalBook, chapter_id: str, new_title: str) -> CanonicalBook:
    title = (new_title or "").strip()
    if not title:
        raise ChapterOpError("Chapter title cannot be empty")
    chapters = []
    found = False
    for ch in book.chapters:
        if ch.id == chapter_id:
            chapters.append(ch.model_copy(update={"title": title}))
            found = True
        else:
            chapters.append(ch)
    if not found:
        raise ChapterOpError(f"Chapter not found: {chapter_id}")
    return book.model_copy(update={"chapters": chapters})


def remove_chapter(book: CanonicalBook, chapter_id: str) -> CanonicalBook:
    chapters = [ch for ch in book.chapters if ch.id != chapter_id]
    if len(chapters) == len(book.chapters):
        raise ChapterOpError(f"Chapter not found: {chapter_id}")
    # Re-order
    chapters = [
        ch.model_copy(update={"order": i}) for i, ch in enumerate(chapters)
    ]
    return book.model_copy(update={"chapters": chapters})


def merge_adjacent(
    book: CanonicalBook,
    left_id: str,
    right_id: str,
    *,
    new_title: str | None = None,
) -> CanonicalBook:
    """Merge two adjacent chapters. Blocks of right are appended to left."""
    idxs = {ch.id: i for i, ch in enumerate(book.chapters)}
    if left_id not in idxs or right_id not in idxs:
        raise ChapterOpError("One or both chapters not found")
    li, ri = idxs[left_id], idxs[right_id]
    if ri != li + 1:
        raise ChapterOpError("Only adjacent chapters can be merged")
    left = book.chapters[li]
    right = book.chapters[ri]
    merged_blocks: list[ContentBlock] = list(left.blocks)
    offset = len(merged_blocks)
    for b in right.blocks:
        merged_blocks.append(b.model_copy(update={"order": offset + b.order}))
    # Normalize order
    merged_blocks = [
        b.model_copy(update={"order": i}) for i, b in enumerate(merged_blocks)
    ]
    title = (new_title or left.title).strip() or left.title
    merged = Chapter(
        id=left.id,
        title=title,
        order=left.order,
        blocks=merged_blocks,
    )
    new_chapters = (
        list(book.chapters[:li]) + [merged] + list(book.chapters[ri + 1 :])
    )
    new_chapters = [
        ch.model_copy(update={"order": i}) for i, ch in enumerate(new_chapters)
    ]
    return book.model_copy(update={"chapters": new_chapters})


def split_chapter(
    book: CanonicalBook,
    chapter_id: str,
    at_block_id: str,
    *,
    new_title: str | None = None,
) -> CanonicalBook:
    """Split one chapter into two at block boundary.

    The block `at_block_id` becomes the first block of the new (right) chapter.
    """
    idx = next((i for i, ch in enumerate(book.chapters) if ch.id == chapter_id), None)
    if idx is None:
        raise ChapterOpError(f"Chapter not found: {chapter_id}")
    ch = book.chapters[idx]
    block_idx = next((i for i, b in enumerate(ch.blocks) if b.id == at_block_id), None)
    if block_idx is None:
        raise ChapterOpError(f"Block not found in chapter: {at_block_id}")
    if block_idx == 0:
        raise ChapterOpError("Cannot split before the first block")

    left_blocks = [
        b.model_copy(update={"order": i}) for i, b in enumerate(ch.blocks[:block_idx])
    ]
    right_blocks = [
        b.model_copy(update={"order": i}) for i, b in enumerate(ch.blocks[block_idx:])
    ]
    left = Chapter(id=ch.id, title=ch.title, order=ch.order, blocks=left_blocks)
    # New id: append _s{n}
    new_id = f"{ch.id}_s{idx + 1}"
    existing = {c.id for c in book.chapters}
    n = 1
    while new_id in existing:
        n += 1
        new_id = f"{ch.id}_s{n}"
    title = (new_title or f"{ch.title} (2)").strip()
    right = Chapter(id=new_id, title=title, order=ch.order + 1, blocks=right_blocks)

    new_chapters = (
        list(book.chapters[:idx]) + [left, right] + list(book.chapters[idx + 1 :])
    )
    new_chapters = [
        c.model_copy(update={"order": i}) for i, c in enumerate(new_chapters)
    ]
    return book.model_copy(update={"chapters": new_chapters})


def reorder_chapters(book: CanonicalBook, ordered_ids: list[str]) -> CanonicalBook:
    """Reorder chapters by id list. All existing ids must appear exactly once."""
    by_id = {ch.id: ch for ch in book.chapters}
    if set(ordered_ids) != set(by_id):
        raise ChapterOpError("ordered_ids must contain each chapter id exactly once")
    chapters = [
        by_id[cid].model_copy(update={"order": i}) for i, cid in enumerate(ordered_ids)
    ]
    return book.model_copy(update={"chapters": chapters})
