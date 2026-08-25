"""Preview corrections must survive into Translation Job (no re-parse)."""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from src.core.chapter_ops import merge_adjacent, rename_chapter
from src.core.pipeline import create_translation_job, parse_to_book
from src.core.storage import Storage
from src.models.job import JobConfig


def _write_simple_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("id-preview")
    book.set_title("Original Title")
    book.set_language("en")
    book.add_author("Author")
    c1 = epub.EpubHtml(title="A", file_name="P001.xhtml", lang="en")
    c1.set_content(
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Alpha</h1><p>First paragraph.</p></body></html>"
    )
    c2 = epub.EpubHtml(title="B", file_name="P002.xhtml", lang="en")
    c2.set_content(
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Beta</h1><p>Second paragraph.</p></body></html>"
    )
    book.add_item(c1)
    book.add_item(c2)
    book.spine = ["nav", c1, c2]
    book.toc = (c1, c2)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


def test_job_uses_normalized_book_not_reparse(tmp_path: Path):
    epub_path = tmp_path / "src.epub"
    _write_simple_epub(epub_path)
    original_bytes = epub_path.read_bytes()

    result = parse_to_book(epub_path, assets_dir=tmp_path / "assets")
    book = result.book
    assert len(book.chapters) >= 2

    first_id = book.chapters[0].id
    book = rename_chapter(book, first_id, "Renamed Chapter One")
    if len(book.chapters) >= 2:
        book = merge_adjacent(book, book.chapters[0].id, book.chapters[1].id)

    storage = Storage(tmp_path / "app.db")
    cfg = JobConfig(target_language="zh-Hant")
    job = create_translation_job(
        None,
        storage,
        cfg,
        work_dir=tmp_path / "job",
        book=book,
    )

    assert job.book.chapters[0].title == "Renamed Chapter One"
    assert len(job.book.chapters) >= 1

    local = rename_chapter(book, job.book.chapters[0].id, "SHOULD NOT APPEAR")
    assert job.book.chapters[0].title == "Renamed Chapter One"
    assert local.chapters[0].title == "SHOULD NOT APPEAR"

    assert epub_path.read_bytes() == original_bytes

    loaded = storage.load_job(job.job_id)
    assert loaded.book.chapters[0].title == "Renamed Chapter One"


def test_job_from_source_still_works(tmp_path: Path):
    epub_path = tmp_path / "src.epub"
    _write_simple_epub(epub_path)
    storage = Storage(tmp_path / "app.db")
    job = create_translation_job(
        epub_path,
        storage,
        JobConfig(),
        work_dir=tmp_path / "job2",
    )
    assert len(job.book.chapters) >= 1
    titles = [c.title for c in job.book.chapters]
    for t in titles:
        assert "P001" not in t
        assert "P002" not in t
