from src.glossary.builder import align_books, extract_term_candidates, AlignmentPair
from src.glossary.matcher import filter_relevant_entries
from src.glossary.models import GlossaryEntry, GlossaryType
from src.glossary.store import GlossaryStore
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter
from pathlib import Path


def _book(texts: list[str]) -> CanonicalBook:
    blocks = [
        ContentBlock(id=f"p{i}", type=BlockType.PARAGRAPH, order=i, text=t)
        for i, t in enumerate(texts)
    ]
    return CanonicalBook(
        metadata=BookMetadata(title="t"),
        chapters=[Chapter(id="ch1", title="c", order=0, blocks=blocks)],
    )


def test_filter_relevant():
    entries = [
        GlossaryEntry(
            id="1", source="Alice", target="愛麗絲", type=GlossaryType.PROPER_NOUN
        ),
        GlossaryEntry(
            id="2", source="Bob", target="鮑勃", type=GlossaryType.PROPER_NOUN
        ),
    ]
    got = filter_relevant_entries(entries, ["Alice went home."])
    assert len(got) == 1
    assert got[0]["target"] == "愛麗絲"


def test_align_mismatch():
    src = _book(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
    tgt = _book(["x"])
    r = align_books(src, tgt)
    assert r.needs_manual_alignment


def test_align_ok_and_candidates():
    src = _book(
        [
            "Alice met Bob in Tokyo.",
            "Alice and Bob again.",
            "Tokyo is big.",
        ]
    )
    tgt = _book(
        [
            "愛麗絲在東京遇見鮑勃。",
            "愛麗絲和鮑勃再次見面。",
            "東京很大。",
        ]
    )
    r = align_books(src, tgt)
    assert not r.needs_manual_alignment
    assert len(r.pairs) == 3
    cands = extract_term_candidates(r.pairs)
    sources = {c.source for c in cands}
    assert "Alice" in sources or "Tokyo" in sources or "Bob" in sources


def test_store_roundtrip(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g = store.create("series-1")
    store.add_entry(g.glossary_id, "Alice", "愛麗絲", confirmed=True)
    loaded = store.load(g.glossary_id)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].target == "愛麗絲"


def test_add_and_edit_entry(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g = store.create("manual")
    e = store.add_entry(g.glossary_id, "Alice", "愛麗絲", confirmed=True)
    assert e.source == "Alice"
    loaded = store.load(g.glossary_id)
    assert len(loaded.entries) == 1
    store.update_entry(g.glossary_id, e.id, source="Alice", target="艾莉絲")
    loaded = store.load(g.glossary_id)
    assert loaded.entries[0].target == "艾莉絲"


def test_rename_glossary(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g = store.create("Old")
    g.name = "New Name"
    store.save(g)
    loaded = store.load(g.glossary_id)
    assert loaded.name == "New Name"


def test_import_creates_independent_glossary(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    original = store.create("Shared Name")
    store.add_entry(original.glossary_id, "Hero", "英雄", confirmed=True)
    export_path = tmp_path / "export_out" / "export.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    store.export_json(original.glossary_id, export_path)

    imported = store.import_json(export_path)
    assert imported.glossary_id != original.glossary_id
    assert imported.name == original.name
    still = store.load(original.glossary_id)
    assert len(still.entries) == 1
    assert still.entries[0].source == "Hero"
    ids = store.list_ids()
    assert original.glossary_id in ids
    assert imported.glossary_id in ids
    assert len(ids) == 2


def test_delete_entry(tmp_path: Path):
    store = GlossaryStore(tmp_path)
    g = store.create("g")
    e = store.add_entry(g.glossary_id, "X", "Y", confirmed=True)
    store.reject_entry(g.glossary_id, e.id)
    loaded = store.load(g.glossary_id)
    assert loaded.entries == []
