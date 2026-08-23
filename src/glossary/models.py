"""Glossary data models (spec §21–§26).

Proper Noun Glossary > Terminology Glossary > Style > AI judgment.
Matching is glossary-as-context (not pure string replace).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GlossaryType(str, Enum):
    PROPER_NOUN = "proper_noun"
    TERMINOLOGY = "terminology"


class GlossaryEntry(BaseModel):
    id: str
    source: str
    target: str
    type: GlossaryType = GlossaryType.PROPER_NOUN
    notes: str | None = None
    confirmed: bool = False
    variants: list[str] = Field(
        default_factory=list,
        description="Common inflections / short forms for pre-filter scan",
    )
    extra: dict[str, Any] = Field(default_factory=dict)


class Glossary(BaseModel):
    glossary_id: str
    name: str
    version: str = "1"
    schema_version: int = 1
    entries: list[GlossaryEntry] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def confirmed_entries(self) -> list[GlossaryEntry]:
        return [e for e in self.entries if e.confirmed]

    def as_prompt_list(self, only_confirmed: bool = True) -> list[dict[str, str]]:
        src = self.confirmed_entries() if only_confirmed else self.entries
        # Proper nouns first
        ordered = sorted(
            src,
            key=lambda e: (0 if e.type == GlossaryType.PROPER_NOUN else 1, e.source),
        )
        return [
            {
                "source": e.source,
                "target": e.target,
                "type": e.type.value,
                **({"notes": e.notes} if e.notes else {}),
            }
            for e in ordered
        ]
