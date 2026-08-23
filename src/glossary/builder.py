"""Glossary Builder — simplified paragraph alignment (spec §22.1).

V1: both docs run through Canonical Book segmentation; pair by index
when counts are similar. Large count mismatch → return unpaired for
manual review (no embedding-based alignment).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

from src.glossary.models import GlossaryEntry, GlossaryType
from src.models.book import CanonicalBook
from src.models.blocks import BlockType


@dataclass
class AlignmentPair:
    index: int
    source_text: str
    target_text: str


@dataclass
class BuilderResult:
    pairs: list[AlignmentPair] = field(default_factory=list)
    unpaired_source: list[str] = field(default_factory=list)
    unpaired_target: list[str] = field(default_factory=list)
    candidates: list[GlossaryEntry] = field(default_factory=list)
    needs_manual_alignment: bool = False
    message: str = ""


def _translatable_texts(book: CanonicalBook) -> list[str]:
    out: list[str] = []
    for ch in book.chapters:
        for b in ch.blocks:
            if b.type in (
                BlockType.PARAGRAPH,
                BlockType.HEADING,
                BlockType.CAPTION,
                BlockType.FOOTNOTE,
            ) and b.text and b.text.strip():
                out.append(b.text.strip())
    return out


def align_books(
    source_book: CanonicalBook,
    target_book: CanonicalBook,
    *,
    mismatch_ratio: float = 0.3,
) -> BuilderResult:
    """Pair blocks by index. Flag for manual review if counts differ a lot."""
    src = _translatable_texts(source_book)
    tgt = _translatable_texts(target_book)
    n_src, n_tgt = len(src), len(tgt)
    if n_src == 0 or n_tgt == 0:
        return BuilderResult(
            unpaired_source=src,
            unpaired_target=tgt,
            needs_manual_alignment=True,
            message="One side has no translatable blocks",
        )

    ratio = abs(n_src - n_tgt) / max(n_src, n_tgt)
    if ratio > mismatch_ratio:
        return BuilderResult(
            unpaired_source=src,
            unpaired_target=tgt,
            needs_manual_alignment=True,
            message=(
                f"Block count mismatch: source={n_src}, target={n_tgt} "
                f"(ratio={ratio:.0%}). Please align manually."
            ),
        )

    n = min(n_src, n_tgt)
    pairs = [
        AlignmentPair(index=i, source_text=src[i], target_text=tgt[i])
        for i in range(n)
    ]
    return BuilderResult(
        pairs=pairs,
        unpaired_source=src[n:],
        unpaired_target=tgt[n:],
        needs_manual_alignment=False,
    )


# Heuristic term extraction: capitalized words / CJK proper-noun-ish runs
_LATIN_PROPER = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,8}")


def extract_term_candidates(
    pairs: list[AlignmentPair],
    *,
    max_candidates: int = 200,
) -> list[GlossaryEntry]:
    """Very lightweight candidate extraction for Review workflow.

    Does not call AI. Collects repeated source tokens that co-occur with
    stable target substrings. Users confirm in Review UI.
    """
    # source term -> set of target paragraphs containing possible translation
    from collections import Counter, defaultdict

    src_counter: Counter[str] = Counter()
    cooccur: dict[str, Counter[str]] = defaultdict(Counter)

    for pair in pairs:
        latin = _LATIN_PROPER.findall(pair.source_text)
        cjk = _CJK_RUN.findall(pair.source_text)
        terms = set(latin + cjk)
        for t in terms:
            if len(t) < 2:
                continue
            src_counter[t] += 1
            # crude: all CJK runs / capitalized tokens in target as candidates
            for tt in _LATIN_PROPER.findall(pair.target_text) + _CJK_RUN.findall(
                pair.target_text
            ):
                if len(tt) >= 2:
                    cooccur[t][tt] += 1

    candidates: list[GlossaryEntry] = []
    for term, count in src_counter.most_common(max_candidates):
        if count < 2:
            continue
        best = cooccur[term].most_common(1)
        target = best[0][0] if best else ""
        if not target or target == term:
            continue
        candidates.append(
            GlossaryEntry(
                id=str(uuid4()),
                source=term,
                target=target,
                type=GlossaryType.PROPER_NOUN,
                confirmed=False,
                notes=f"auto-candidate (freq={count})",
            )
        )
    return candidates


def build_candidates_from_alignment(
    source_book: CanonicalBook,
    target_book: CanonicalBook,
) -> BuilderResult:
    result = align_books(source_book, target_book)
    if result.pairs and not result.needs_manual_alignment:
        result.candidates = extract_term_candidates(result.pairs)
    return result
