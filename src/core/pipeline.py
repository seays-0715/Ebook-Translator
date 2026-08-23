"""High-level convert / translate pipelines."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.core.storage import Storage
from src.epub.generator import generate_epub
from src.epub.validator import validate_epub_file
from src.models.job import JobConfig, JobStatus, TranslationJob
from src.parsers.epub_parser import parse_epub
from src.parsers.txt_parser import parse_txt
from src.translation.book_validator import validate_canonical_book
from src.translation.engine import TranslationEngine


def convert_file(
    source: str | Path,
    output: str | Path,
    *,
    assets_dir: Path | None = None,
) -> Path:
    """Parse → Canonical Book → clean EPUB (no translation)."""
    source = Path(source)
    assets_dir = assets_dir or source.parent / f".assets_{source.stem}"
    if source.suffix.lower() == ".epub":
        result = parse_epub(source, assets_dir=assets_dir)
    elif source.suffix.lower() == ".txt":
        result = parse_txt(source)
    else:
        raise ValueError(f"Unsupported format: {source.suffix}")
    return generate_epub(result.book, output, assets_base=assets_dir)


def parse_to_book(source: str | Path, assets_dir: Path | None = None):
    source = Path(source)
    assets_dir = assets_dir or source.parent / f".assets_{source.stem}"
    if source.suffix.lower() == ".epub":
        return parse_epub(source, assets_dir=assets_dir)
    if source.suffix.lower() == ".txt":
        return parse_txt(source)
    raise ValueError(f"Unsupported format: {source.suffix}")


def create_translation_job(
    source: str | Path,
    storage: Storage,
    config: JobConfig,
    *,
    work_dir: Path,
) -> TranslationJob:
    source = Path(source)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = work_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    result = parse_to_book(source, assets_dir=assets_dir)

    job_id = str(uuid4())
    book_id = job_id  # 1:1 snapshot
    storage.save_book(result.book, book_id=book_id)
    now = datetime.now(timezone.utc).isoformat()
    job = TranslationJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        config=config,
        book=result.book,
        storage_dir=str(work_dir),
        created_at=now,
        updated_at=now,
    )
    object.__setattr__(job, "_book_id", book_id)
    storage.save_job(job)
    return job


def run_translation_job(
    storage: Storage,
    job_id: str,
    *,
    glossary: list[dict[str, str]] | None = None,
    on_progress=None,
) -> JobStatus:
    job = storage.load_job(job_id)
    object.__setattr__(job, "_book_id", job_id)
    engine = TranslationEngine(
        storage, job, glossary_entries=glossary, on_progress=on_progress
    )
    return engine.run()


def export_job_epub(
    storage: Storage,
    job_id: str,
    output: str | Path,
    *,
    force: bool = False,
) -> Path:
    """Export translated EPUB.

    Runs Level 2 validation. On failure:
      - force=False → raise, keep checkpoints
      - force=True  → export anyway (Force Export, spec §32.3)
    Level 3 checks the written file.
    """
    job = storage.load_job(job_id)
    object.__setattr__(job, "_book_id", job_id)
    engine = TranslationEngine(storage, job)
    book = engine.apply_all_translations_to_book()
    chunks = storage.load_chunks(job_id)

    level2 = validate_canonical_book(
        book, chunks=chunks, require_translations=True
    )
    if not level2.ok and not force:
        raise RuntimeError(
            "Level 2 validation failed:\n"
            + "\n".join(level2.errors)
            + "\nUse force=True to Force Export (may be incomplete)."
        )

    out = generate_epub(book, output)
    level3 = validate_epub_file(out)
    if not level3.ok and not force:
        raise RuntimeError(
            "Level 3 EPUB validation failed:\n" + "\n".join(level3.errors)
        )
    return out
