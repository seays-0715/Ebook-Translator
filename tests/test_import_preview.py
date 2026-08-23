"""Regression: open/analyze path used by Convert \u2192 Preview."""

from __future__ import annotations

from pathlib import Path

from src.core.pipeline import parse_to_book
from src.ui.paths import assets_dir_for, data_dir, ebook_filetypes


def test_data_dir_is_under_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = data_dir()
    assert d == tmp_path / ".ebook_translator"
    assert d.is_dir()


def test_assets_dir_writable_under_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    src = tmp_path / "readonly" / "book.epub"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"PK")
    assets = assets_dir_for(src)
    assert assets.is_dir()
    assert str(assets).startswith(str(tmp_path / ".ebook_translator"))
    probe = assets / "probe.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"


def test_parse_txt_to_preview_book(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text(
        "Chapter 1\n\nHello world.\n\nChapter 2\n\nSecond chapter text.\n",
        encoding="utf-8",
    )
    result = parse_to_book(p, assets_dir=tmp_path / "assets")
    assert result.book is not None
    assert len(result.book.chapters) >= 1
    assert any(ch.blocks for ch in result.book.chapters)


def test_ebook_filetypes_non_empty():
    fts = ebook_filetypes("Ebook", "EPUB", "All")
    assert len(fts) >= 2
    joined = " ".join(p for _, p in fts)
    assert "*.epub" in joined
