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
    source: str | Path | None,
    storage: Storage,
    config: JobConfig,
    *,
    work_dir: Path,
    book=None,
    glossary_entries: list[dict[str, str]] | None = None,
    glossary_version: str | None = None,
) -> TranslationJob:
    """Create job with full immutable config + book snapshot.

    Prefer an already-normalized Canonical Book (from Preview corrections).
    Only re-parse *source* when *book* is not provided.

    Original input is never modified. Optional glossary_entries are frozen
    into config at creation time.
    """
    from src.models.book import CanonicalBook

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = work_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    if book is not None:
        if not isinstance(book, CanonicalBook):
            raise TypeError("book must be a CanonicalBook")
        # Deep-copy snapshot so later Preview edits cannot mutate this Job
        snapshot = CanonicalBook.model_validate(book.model_dump())
        # Copy referenced asset files into job work dir when paths are external
        new_assets: dict[str, str] = {}
        for key, rel in (snapshot.assets or {}).items():
            src_path = Path(rel)
            if src_path.is_file():
                dest = assets_dir / src_path.name
                if src_path.resolve() != dest.resolve():
                    dest.write_bytes(src_path.read_bytes())
                new_assets[key] = str(dest)
            else:
                new_assets[key] = rel
        snapshot = snapshot.model_copy(update={"assets": new_assets})
    else:
        if source is None:
            raise ValueError("Either book or source must be provided")
        source = Path(source)
        result = parse_to_book(source, assets_dir=assets_dir)
        snapshot = result.book

    # Freeze glossary into config snapshot (copy; do not keep live reference)
    if glossary_entries is not None:
        config = config.model_copy(
            update={
                "glossary_entries": [dict(e) for e in glossary_entries],
                "glossary_version": glossary_version or config.glossary_version,
            }
        )
    elif glossary_version is not None:
        config = config.model_copy(update={"glossary_version": glossary_version})

    job_id = str(uuid4())
    book_id = job_id  # 1:1 book snapshot owned by this job
    storage.save_book(snapshot, book_id=book_id)
    now = datetime.now(timezone.utc).isoformat()
    job = TranslationJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        config=config,
        book=snapshot,
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
    on_progress=None,
) -> JobStatus:
    """Run / resume using only the Job's frozen config (incl. glossary snapshot).

    Callers must not inject a different glossary here. To use a new glossary,
    create a new Job.
    """
    job = storage.load_job(job_id)
    object.__setattr__(job, "_book_id", job_id)
    engine = TranslationEngine(storage, job, on_progress=on_progress)
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
