"""Level 2 — Canonical Book Validation (spec §32.1).

Checks chapter/block structure, image references, translation completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.blocks import BlockType
from src.models.book import CanonicalBook
from src.models.chunk import Chunk, ChunkStatus


@dataclass
class BookValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_canonical_book(
    book: CanonicalBook,
    *,
    chunks: list[Chunk] | None = None,
    require_translations: bool = False,
) -> BookValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not book.chapters:
        errors.append("Book has no chapters")

    seen_block_ids: set[str] = set()
    for ch in book.chapters:
        if not ch.title or not ch.title.strip():
            warnings.append(f"Chapter {ch.id} has empty title")
        for b in ch.blocks:
            if b.id in seen_block_ids:
                errors.append(f"Duplicate block id: {b.id}")
            seen_block_ids.add(b.id)
            if b.type == BlockType.IMAGE:
                if not b.image_ref:
                    warnings.append(f"Image block {b.id} has no image_ref")
                elif b.image_ref not in book.assets:
                    # assets may key by original path; soft warning
                    warnings.append(
                        f"Image block {b.id} ref '{b.image_ref}' not in assets map"
                    )
            if b.is_translatable() and require_translations:
                if not b.text or not b.text.strip():
                    errors.append(f"Empty text on translatable block {b.id}")

    if chunks is not None and require_translations:
        failed = [c for c in chunks if c.status == ChunkStatus.FAILED]
        pending = [
            c
            for c in chunks
            if c.status in (ChunkStatus.PENDING, ChunkStatus.IN_PROGRESS)
        ]
        if failed:
            # Group by chapter for clearer message
            by_ch: dict[str, int] = {}
            for c in failed:
                by_ch[c.chapter_id] = by_ch.get(c.chapter_id, 0) + 1
            for ch_id, n in sorted(by_ch.items()):
                errors.append(f"Chapter {ch_id}: {n} failed chunk(s)")
        if pending:
            errors.append(f"{len(pending)} chunk(s) still pending/in_progress")

        # Completeness: every translatable block should appear in a completed chunk
        completed_ids: set[str] = set()
        for c in chunks:
            if c.status == ChunkStatus.COMPLETED:
                completed_ids.update(c.translated_texts.keys())
        expected = {b.id for _, b in book.all_translatable_blocks()}
        missing = expected - completed_ids
        if missing:
            errors.append(f"{len(missing)} translatable block(s) lack completed translation")

    return BookValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def validate_assets_exist(book: CanonicalBook) -> BookValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for key, rel in book.assets.items():
        if not Path(rel).exists():
            errors.append(f"Asset missing on disk: {key} -> {rel}")
    return BookValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
