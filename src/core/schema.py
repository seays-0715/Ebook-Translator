"""SQLite schema for Canonical Book + Jobs + Chunks.

schema_version is for identification only.
No migration framework: unsupported versions are rejected; user must recreate job.
"""

SCHEMA_VERSION = 1

CREATE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS books (
        book_id        TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        metadata_json  TEXT NOT NULL,
        cover_ref      TEXT,
        layout         TEXT NOT NULL DEFAULT 'horizontal',
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chapters (
        book_id    TEXT NOT NULL,
        chapter_id TEXT NOT NULL,
        title      TEXT NOT NULL,
        ord        INTEGER NOT NULL,
        PRIMARY KEY (book_id, chapter_id),
        FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS blocks (
        book_id    TEXT NOT NULL,
        chapter_id TEXT NOT NULL,
        block_id   TEXT NOT NULL,
        type       TEXT NOT NULL,
        ord        INTEGER NOT NULL,
        text       TEXT,
        image_ref  TEXT,
        image_alt  TEXT,
        level      INTEGER,
        attrs_json TEXT,
        PRIMARY KEY (book_id, block_id),
        FOREIGN KEY (book_id, chapter_id) REFERENCES chapters(book_id, chapter_id)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        book_id    TEXT NOT NULL,
        asset_key  TEXT NOT NULL,
        rel_path   TEXT NOT NULL,
        PRIMARY KEY (book_id, asset_key),
        FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id            TEXT PRIMARY KEY,
        schema_version    INTEGER NOT NULL,
        status            TEXT NOT NULL,
        config_json       TEXT NOT NULL,
        book_id           TEXT NOT NULL,
        storage_dir       TEXT NOT NULL,
        output_path       TEXT,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL,
        started_at        TEXT,
        finished_at       TEXT,
        total_chunks      INTEGER NOT NULL DEFAULT 0,
        completed_chunks  INTEGER NOT NULL DEFAULT 0,
        failed_chunks     INTEGER NOT NULL DEFAULT 0,
        error_summary     TEXT,
        FOREIGN KEY (book_id) REFERENCES books(book_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        job_id                TEXT NOT NULL,
        chunk_id              TEXT NOT NULL,
        chapter_id            TEXT NOT NULL,
        block_ids_json        TEXT NOT NULL,
        carry_over_source_json TEXT,
        carry_over_translated_json TEXT,
        source_texts_json     TEXT NOT NULL,
        translated_texts_json TEXT,
        status                TEXT NOT NULL,
        error_message         TEXT,
        attempt_count         INTEGER NOT NULL DEFAULT 0,
        token_estimate        INTEGER NOT NULL DEFAULT 0,
        created_at            TEXT,
        updated_at            TEXT,
        PRIMARY KEY (job_id, chunk_id),
        FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_blocks_chapter
        ON blocks(book_id, chapter_id, ord)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chunks_status
        ON chunks(job_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chapters_ord
        ON chapters(book_id, ord)
    """,
]
