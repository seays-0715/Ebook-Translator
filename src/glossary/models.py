"""Glossary data models (spec §21–§26).

Matching is glossary-as-context (not pure string replace).
UI may expose two independent selection slots (labeled Global / Book);
they are not different glossary types — any glossary can fill either slot.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GlossaryType(str, Enum):
    """Optional entry tag for display/ordering only — does not change match semantics."""

    PROPER_NOUN = "proper_noun"
    TERMINOLOGY = "terminology"


class GlossaryScope(str, Enum):
    """Legacy optional label on a Glossary record.

    UI "Global Glossary" / "Book Glossary" are two independent selection slots,
    not two different glossary types. Any Glossary may fill either slot.
    Scope is not used to change term behavior.
    """

    GLOBAL = "global"
    BOOK = "book"


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
    # Optional legacy label only; not a behavioral scope
    scope: GlossaryScope = GlossaryScope.GLOBAL
    book_key: str | None = None
    version: str = "1"
    schema_version: int = 1
    entries: list[GlossaryEntry] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def confirmed_entries(self) -> list[GlossaryEntry]:
        return [e for e in self.entries if e.confirmed]

    def as_prompt_list(self, only_confirmed: bool = True) -> list[dict[str, str]]:
        src = self.confirmed_entries() if only_confirmed else self.entries
        # Stable order: proper_noun tag first (display preference only)
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
