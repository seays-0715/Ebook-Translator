"""Context-aware chunk builder.

Rules (spec §20.1):
1. Never split mid-block
2. Prefer keeping continuous dialogue together
3. Prefer chapter boundaries over chunk size
4. Target 800–1200 source tokens (content only)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.models.book import CanonicalBook
from src.models.chunk import Chunk, ChunkStatus
from src.translation.tokens import count_tokens, estimate_tokens as _estimate


def estimate_tokens(text: str) -> int:  # retained for tests / fallback callers
    return _estimate(text)


def build_chunks(
    book: CanonicalBook,
    *,
    target_tokens: int = 1000,
    carry_over_paragraphs: int = 2,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    prev_tail_source: list[dict[str, str]] = []
    prev_tail_translated: list[dict[str, str]] = []  # empty at build time

    for ch in book.chapters:
        translatable = [b for b in ch.blocks if b.is_translatable()]
        if not translatable:
            continue

        current_ids: list[str] = []
        current_texts: dict[str, str] = {}
        current_tokens = 0

        def flush() -> None:
            nonlocal current_ids, current_texts, current_tokens
            nonlocal prev_tail_source, prev_tail_translated
            if not current_ids:
                return
            cid = f"c_{ch.id}_{uuid4().hex[:8]}"
            chunk = Chunk(
                chunk_id=cid,
                chapter_id=ch.id,
                block_ids=list(current_ids),
                carry_over_source=list(prev_tail_source),
                carry_over_translated=list(prev_tail_translated),
                source_texts=dict(current_texts),
                status=ChunkStatus.PENDING,
                token_estimate=current_tokens,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            chunks.append(chunk)
            # Update carry-over tail
            tail_n = min(carry_over_paragraphs, len(current_ids))
            prev_tail_source = [
                {"id": bid, "text": current_texts[bid]}
                for bid in current_ids[-tail_n:]
            ]
            # Translations filled later by engine after previous chunk completes (§20.1)
            prev_tail_translated = []
            current_ids = []
            current_texts = {}
            current_tokens = 0

        for b in translatable:
            t = count_tokens(b.text or "")
            if current_ids and current_tokens + t > target_tokens:
                flush()
            current_ids.append(b.id)
            current_texts[b.id] = b.text or ""
            current_tokens += t

        flush()
        # Reset carry-over across chapters (chapter boundary preferred)
        prev_tail_source = []
        prev_tail_translated = []

    return chunks
