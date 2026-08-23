"""File-based Glossary store (JSON). Import/Export friendly (spec §25)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.glossary.models import Glossary, GlossaryEntry, GlossaryType


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GlossaryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, glossary_id: str) -> Path:
        return self.root / f"{glossary_id}.json"

    def save(self, glossary: Glossary) -> None:
        glossary.updated_at = _utcnow()
        if not glossary.created_at:
            glossary.created_at = glossary.updated_at
        path = self._path(glossary.glossary_id)
        path.write_text(
            glossary.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self, glossary_id: str) -> Glossary:
        path = self._path(glossary_id)
        if not path.exists():
            raise KeyError(f"Glossary not found: {glossary_id}")
        return Glossary.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

    def create(
        self,
        name: str,
        *,
        version: str = "1",
        entries: list[GlossaryEntry] | None = None,
    ) -> Glossary:
        g = Glossary(
            glossary_id=str(uuid4()),
            name=name,
            version=version,
            entries=entries or [],
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self.save(g)
        return g

    def export_json(self, glossary_id: str, dest: str | Path) -> Path:
        g = self.load(glossary_id)
        dest = Path(dest)
        dest.write_text(g.model_dump_json(indent=2), encoding="utf-8")
        return dest

    def import_json(self, path: str | Path, *, new_id: bool = True) -> Glossary:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        g = Glossary.model_validate(data)
        if new_id:
            g.glossary_id = str(uuid4())
        self.save(g)
        return g

    def add_entry(
        self,
        glossary_id: str,
        source: str,
        target: str,
        *,
        type: GlossaryType = GlossaryType.PROPER_NOUN,
        confirmed: bool = False,
        notes: str | None = None,
        variants: list[str] | None = None,
    ) -> GlossaryEntry:
        g = self.load(glossary_id)
        entry = GlossaryEntry(
            id=str(uuid4()),
            source=source,
            target=target,
            type=type,
            confirmed=confirmed,
            notes=notes,
            variants=variants or [],
        )
        g.entries.append(entry)
        self.save(g)
        return entry

    def confirm_entry(self, glossary_id: str, entry_id: str, confirmed: bool = True) -> None:
        g = self.load(glossary_id)
        for e in g.entries:
            if e.id == entry_id:
                e.confirmed = confirmed
                self.save(g)
                return
        raise KeyError(entry_id)
