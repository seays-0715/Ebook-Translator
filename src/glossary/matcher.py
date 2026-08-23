"""Glossary pre-filter for chunk prompts (spec §26.1).

Scan chunk text with simple string / variant matching (宁滥勿缺),
then pass candidates to AI as context — no forced string replace.
"""

from __future__ import annotations

from src.glossary.models import GlossaryEntry


def filter_relevant_entries(
    entries: list[GlossaryEntry] | list[dict],
    texts: list[str],
) -> list[dict[str, str]]:
    """Return glossary dicts that appear (or whose variants appear) in any text."""
    if not entries or not texts:
        return []
    joined = "\n".join(texts)
    result: list[dict[str, str]] = []
    seen: set[str] = set()

    for e in entries:
        if isinstance(e, dict):
            source = e.get("source") or ""
            variants = e.get("variants") or []
            target = e.get("target") or ""
            etype = e.get("type") or "proper_noun"
            notes = e.get("notes")
            key = source
        else:
            source = e.source
            variants = e.variants
            target = e.target
            etype = e.type.value
            notes = e.notes
            key = e.id if hasattr(e, "id") else source

        if not source:
            continue
        needles = [source] + list(variants)
        hit = any(n and n in joined for n in needles)
        if hit and key not in seen:
            seen.add(key)
            item = {"source": source, "target": target, "type": etype}
            if notes:
                item["notes"] = notes
            result.append(item)
    return result
