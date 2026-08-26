"""SQLite-backed storage for Canonical Book, Jobs, and Chunks.

Uses WAL mode for crash safety. Single database file per workspace or per job
as needed. No migration framework — unsupported schema_version is rejected.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable
from uuid import uuid4

from src.core.schema import CREATE_STATEMENTS, SCHEMA_VERSION
from src.models.blocks import BlockType, ContentBlock
from src.models.book import BookMetadata, CanonicalBook, Chapter, Layout
from src.models.chunk import Chunk, ChunkStatus
from src.models.job import JobConfig, JobStatus, TranslationJob


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _json_loads(s: str | None) -> Any:
    if s is None or s == "":
        return None
    return json.loads(s)


class Storage:
    """Thin SQLite access layer. One instance owns one database file."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._tx() as conn:
            for stmt in CREATE_STATEMENTS:
                conn.execute(stmt)
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            else:
                ver = int(row["value"])
                if ver != SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Unsupported schema version {ver}; "
                        f"current is {SCHEMA_VERSION}. Recreate the database."
                    )

    def save_book(self, book: CanonicalBook, book_id: str | None = None) -> str:
        book_id = book_id or str(uuid4())
        now = _utcnow()
        with self._tx() as conn:
            conn.execute("DELETE FROM assets WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM blocks WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
            conn.execute(
                """
                INSERT INTO books
                    (book_id, schema_version, metadata_json, cover_ref, layout,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id, book.schema_version, book.metadata.model_dump_json(),
                    book.cover_ref, book.layout.value, now, now,
                ),
            )
            for ch in book.chapters:
                conn.execute(
                    "INSERT INTO chapters (book_id, chapter_id, title, ord) VALUES (?, ?, ?, ?)",
                    (book_id, ch.id, ch.title, ch.order),
                )
                for b in ch.blocks:
                    conn.execute(
                        """
                        INSERT INTO blocks
                            (book_id, chapter_id, block_id, type, ord, text,
                             image_ref, image_alt, level, attrs_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            book_id, ch.id, b.id, b.type.value, b.order, b.text,
                            b.image_ref, b.image_alt, b.level,
                            _json_dumps(b.attrs) if b.attrs else None,
                        ),
                    )
            for key, rel in book.assets.items():
                conn.execute(
                    "INSERT INTO assets (book_id, asset_key, rel_path) VALUES (?, ?, ?)",
                    (book_id, key, rel),
                )
        return book_id

    def load_book(self, book_id: str) -> CanonicalBook:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
            if row is None:
                raise KeyError(f"Book not found: {book_id}")
            if int(row["schema_version"]) != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported book schema version {row['schema_version']}")
            meta = BookMetadata.model_validate_json(row["metadata_json"])
            chapters_rows = conn.execute(
                "SELECT * FROM chapters WHERE book_id = ? ORDER BY ord", (book_id,)
            ).fetchall()
            chapters: list[Chapter] = []
            for cr in chapters_rows:
                blocks_rows = conn.execute(
                    "SELECT * FROM blocks WHERE book_id = ? AND chapter_id = ? ORDER BY ord",
                    (book_id, cr["chapter_id"]),
                ).fetchall()
                blocks = [
                    ContentBlock(
                        id=br["block_id"], type=BlockType(br["type"]), order=br["ord"],
                        text=br["text"], image_ref=br["image_ref"], image_alt=br["image_alt"],
                        level=br["level"], attrs=_json_loads(br["attrs_json"]) or {},
                    )
                    for br in blocks_rows
                ]
                chapters.append(Chapter(id=cr["chapter_id"], title=cr["title"], order=cr["ord"], blocks=blocks))
            asset_rows = conn.execute(
                "SELECT asset_key, rel_path FROM assets WHERE book_id = ?", (book_id,)
            ).fetchall()
            assets = {r["asset_key"]: r["rel_path"] for r in asset_rows}
            return CanonicalBook(
                schema_version=int(row["schema_version"]), metadata=meta,
                cover_ref=row["cover_ref"], layout=Layout(row["layout"]),
                chapters=chapters, assets=assets,
            )

    def save_job(self, job: TranslationJob) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, schema_version, status, config_json, book_id,
                    storage_dir, output_path, created_at, updated_at,
                    started_at, finished_at, total_chunks, completed_chunks,
                    failed_chunks, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    config_json = excluded.config_json,
                    output_path = excluded.output_path,
                    updated_at = excluded.updated_at,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    total_chunks = excluded.total_chunks,
                    completed_chunks = excluded.completed_chunks,
                    failed_chunks = excluded.failed_chunks,
                    error_summary = excluded.error_summary
                """,
                (
                    job.job_id, job.schema_version, job.status.value,
                    job.config.model_dump_json(), getattr(job, "_book_id", job.job_id),
                    job.storage_dir, job.output_path, job.created_at or now, now,
                    job.started_at, job.finished_at, job.total_chunks,
                    job.completed_chunks, job.failed_chunks, job.error_summary,
                ),
            )

    def load_job(self, job_id: str) -> TranslationJob:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            if int(row["schema_version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported job schema version {row['schema_version']}. Recreate the job."
                )
            book = self.load_book(row["book_id"])
            return TranslationJob(
                job_id=row["job_id"], schema_version=int(row["schema_version"]),
                status=JobStatus(row["status"]),
                config=JobConfig.model_validate_json(row["config_json"]),
                book=book, storage_dir=row["storage_dir"], output_path=row["output_path"],
                created_at=row["created_at"], updated_at=row["updated_at"],
                started_at=row["started_at"], finished_at=row["finished_at"],
                total_chunks=row["total_chunks"], completed_chunks=row["completed_chunks"],
                failed_chunks=row["failed_chunks"], error_summary=row["error_summary"],
            )

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._tx() as conn:
            rows = conn.execute(
                """
                SELECT job_id, status, created_at, updated_at,
                       total_chunks, completed_chunks, failed_chunks,
                       error_summary
                FROM jobs ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        """Return unfinished jobs suitable for recovery after EXE restart.

        Includes PENDING, PAUSED, PROCESSING, COMPLETED_WITH_ERRORS.
        Excludes COMPLETED and CANCELLED (terminal).
        Joins books for display title; progress from chunk counters.
        """
        with self._tx() as conn:
            rows = conn.execute(
                """
                SELECT j.job_id, j.status, j.created_at, j.updated_at,
                       j.total_chunks, j.completed_chunks, j.failed_chunks,
                       j.error_summary, j.output_path, j.storage_dir,
                       j.config_json,
                       COALESCE(
                           json_extract(b.metadata_json, '$.title'),
                           j.job_id
                       ) AS title
                FROM jobs j
                LEFT JOIN books b ON b.book_id = j.book_id
                WHERE j.status IN ('pending', 'paused', 'processing', 'completed_with_errors')
                ORDER BY j.updated_at DESC
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                result.append(d)
            return result

    def delete_job(self, job_id: str) -> None:
        """Permanently remove job row, chunks, and book snapshot."""
        with self._tx() as conn:
            conn.execute("DELETE FROM chunks WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM books WHERE book_id = ?", (job_id,))

    def update_job_status(
        self, job_id: str, status: JobStatus, *,
        error_summary: str | None = None, finished: bool = False,
    ) -> None:
        now = _utcnow()
        with self._tx() as conn:
            if finished:
                conn.execute(
                    """
                    UPDATE jobs SET status = ?, updated_at = ?, finished_at = ?,
                           error_summary = COALESCE(?, error_summary)
                    WHERE job_id = ?
                    """,
                    (status.value, now, now, error_summary, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs SET status = ?, updated_at = ?,
                           error_summary = COALESCE(?, error_summary)
                    WHERE job_id = ?
                    """,
                    (status.value, now, error_summary, job_id),
                )

    def update_job_progress(
        self, job_id: str, completed: int, failed: int, total: int | None = None
    ) -> None:
        now = _utcnow()
        with self._tx() as conn:
            if total is not None:
                conn.execute(
                    """
                    UPDATE jobs SET completed_chunks = ?, failed_chunks = ?,
                           total_chunks = ?, updated_at = ? WHERE job_id = ?
                    """,
                    (completed, failed, total, now, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs SET completed_chunks = ?, failed_chunks = ?,
                           updated_at = ? WHERE job_id = ?
                    """,
                    (completed, failed, now, job_id),
                )

    def save_chunks(self, job_id: str, chunks: Iterable[Chunk]) -> None:
        now = _utcnow()
        with self._tx() as conn:
            for c in chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (
                        job_id, chunk_id, chapter_id, block_ids_json,
                        carry_over_source_json, carry_over_translated_json,
                        source_texts_json, translated_texts_json, status,
                        error_message, attempt_count, token_estimate,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, chunk_id) DO UPDATE SET
                        translated_texts_json = excluded.translated_texts_json,
                        status = excluded.status,
                        error_message = excluded.error_message,
                        attempt_count = excluded.attempt_count,
                        updated_at = excluded.updated_at,
                        carry_over_translated_json = excluded.carry_over_translated_json
                    """,
                    (
                        job_id, c.chunk_id, c.chapter_id, _json_dumps(c.block_ids),
                        _json_dumps(c.carry_over_source), _json_dumps(c.carry_over_translated),
                        _json_dumps(c.source_texts), _json_dumps(c.translated_texts),
                        c.status.value, c.error_message, c.attempt_count, c.token_estimate,
                        c.created_at or now, now,
                    ),
                )

    def load_chunks(self, job_id: str) -> list[Chunk]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE job_id = ? ORDER BY rowid", (job_id,)
            ).fetchall()
            result: list[Chunk] = []
            for r in rows:
                result.append(
                    Chunk(
                        chunk_id=r["chunk_id"], chapter_id=r["chapter_id"],
                        block_ids=_json_loads(r["block_ids_json"]) or [],
                        carry_over_source=_json_loads(r["carry_over_source_json"]) or [],
                        carry_over_translated=_json_loads(r["carry_over_translated_json"]) or [],
                        source_texts=_json_loads(r["source_texts_json"]) or {},
                        translated_texts=_json_loads(r["translated_texts_json"]) or {},
                        status=ChunkStatus(r["status"]), error_message=r["error_message"],
                        attempt_count=r["attempt_count"], token_estimate=r["token_estimate"],
                        created_at=r["created_at"], updated_at=r["updated_at"],
                    )
                )
            return result

    def load_pending_chunks(self, job_id: str) -> list[Chunk]:
        chunks = self.load_chunks(job_id)
        return [c for c in chunks if c.status in (ChunkStatus.PENDING, ChunkStatus.FAILED)]

    def update_chunk(self, job_id: str, chunk: Chunk) -> None:
        self.save_chunks(job_id, [chunk])
