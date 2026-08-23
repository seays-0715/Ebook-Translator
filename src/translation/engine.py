"""Translation engine — sequential chunk processing with checkpointing.

V1: sequential only (spec §43). Pause waits for current request to finish.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

from src.core.storage import Storage
from src.models.blocks import ContentBlock
from src.models.book import CanonicalBook
from src.models.chunk import Chunk, ChunkStatus
from src.models.job import JobStatus, TranslationJob
from src.translation.chunker import build_chunks
from src.translation.client import TranslationClient, TranslationError
from src.translation.prompts import DEFAULT_SYSTEM_PROMPT, build_user_payload
from src.translation.validator import validate_ai_response
from src.utils.power import SleepPreventer

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, dict], None]


class TranslationEngine:
    def __init__(
        self,
        storage: Storage,
        job: TranslationJob,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Execute using Job snapshot only (config + book + glossary_entries).

        Glossary and prompt come from job.config; callers cannot override them
        for an existing job (spec: immutable after first execution).
        """
        self.storage = storage
        self.job = job
        # Always from Job snapshot — never current/global glossary
        self.glossary_entries = list(job.config.glossary_entries or [])
        self.system_prompt = job.config.prompt or DEFAULT_SYSTEM_PROMPT
        self.on_progress = on_progress
        self._stop_requested = False
        self._pause_requested = False
        self._client = TranslationClient(job.config)
        self._consecutive_conn_fails = 0

    def request_pause(self) -> None:
        self._pause_requested = True

    def request_stop(self) -> None:
        self._stop_requested = True

    def prepare_chunks(self) -> list[Chunk]:
        existing = self.storage.load_chunks(self.job.job_id)
        if existing:
            return existing
        chunks = build_chunks(
            self.job.book,
            target_tokens=self.job.config.chunk_target_tokens,
            carry_over_paragraphs=self.job.config.carry_over_paragraphs,
        )
        self.storage.save_chunks(self.job.job_id, chunks)
        self.storage.update_job_progress(
            self.job.job_id, completed=0, failed=0, total=len(chunks)
        )
        return chunks

    def run(self) -> JobStatus:
        """Process all pending/failed chunks. Returns final job status."""
        sleep_guard = SleepPreventer()
        sleep_guard.prevent()
        try:
            return self._run_inner()
        finally:
            sleep_guard.restore()

    def retry_failed_chunks(self, chunk_ids: list[str] | None = None) -> JobStatus:
        """Re-queue failed chunks (all or selected) and run. Spec §31."""
        chunks = self.storage.load_chunks(self.job.job_id)
        for c in chunks:
            if c.status != ChunkStatus.FAILED:
                continue
            if chunk_ids is not None and c.chunk_id not in chunk_ids:
                continue
            c.status = ChunkStatus.PENDING
            c.error_message = None
            self.storage.update_chunk(self.job.job_id, c)
        return self.run()

    def _run_inner(self) -> JobStatus:
        chunks = self.prepare_chunks()
        self.storage.update_job_status(self.job.job_id, JobStatus.PROCESSING)
        self.job.status = JobStatus.PROCESSING
        if not self.job.started_at:
            self.job.started_at = datetime.now(timezone.utc).isoformat()
            self.storage.save_job(self.job)

        for chunk in chunks:
            if self._stop_requested:
                self.storage.update_job_status(self.job.job_id, JobStatus.CANCELLED)
                return JobStatus.CANCELLED
            if self._pause_requested:
                self.storage.update_job_status(self.job.job_id, JobStatus.PAUSED)
                return JobStatus.PAUSED
            if chunk.status == ChunkStatus.COMPLETED:
                continue

            self._process_one(chunk)
            time.sleep(self.job.config.request_interval_seconds)

            if self._consecutive_conn_fails >= self.job.config.endpoint_fail_threshold:
                logger.error("Endpoint appears down; auto-pausing job")
                self.storage.update_job_status(
                    self.job.job_id,
                    JobStatus.PAUSED,
                    error_summary=(
                        f"Cannot connect to Local AI ({self.job.config.endpoint}). "
                        "Job auto-paused."
                    ),
                )
                return JobStatus.PAUSED

        # Final status
        all_chunks = self.storage.load_chunks(self.job.job_id)
        completed = sum(1 for c in all_chunks if c.status == ChunkStatus.COMPLETED)
        failed = sum(1 for c in all_chunks if c.status == ChunkStatus.FAILED)
        self.storage.update_job_progress(self.job.job_id, completed, failed)

        if failed == 0:
            status = JobStatus.COMPLETED
        else:
            status = JobStatus.COMPLETED_WITH_ERRORS
        self.storage.update_job_status(self.job.job_id, status, finished=True)
        return status

    def _process_one(self, chunk: Chunk) -> None:
        chunk.status = ChunkStatus.IN_PROGRESS
        chunk.attempt_count += 1
        self.storage.update_chunk(self.job.job_id, chunk)
        self._emit("chunk_start", {"chunk_id": chunk.chunk_id})

        to_translate = [
            {"id": bid, "text": chunk.source_texts[bid]} for bid in chunk.block_ids
        ]
        # Glossary pre-filter (spec §26.1): string/variant scan, AI decides application
        from src.glossary.matcher import filter_relevant_entries
        texts = [chunk.source_texts.get(bid) or "" for bid in chunk.block_ids]
        relevant_glossary = filter_relevant_entries(self.glossary_entries, texts)
        payload = build_user_payload(
            source_lang=self.job.config.source_language,
            target_lang=self.job.config.target_language,
            style=self.job.config.style,
            glossary_entries=relevant_glossary,
            carry_over=chunk.carry_over_source,
            to_translate=to_translate,
        )

        try:
            raw = self._client.with_retry(
                lambda: self._client.translate_chunk(
                    system_prompt=self.system_prompt,
                    user_payload=payload,
                )
            )
            result = validate_ai_response(chunk.block_ids, raw)
            if not result.ok:
                raise TranslationError(
                    "Validation failed: " + "; ".join(result.errors),
                    retryable=False,
                )
            chunk.translated_texts = result.translations
            chunk.status = ChunkStatus.COMPLETED
            chunk.error_message = None
            self._consecutive_conn_fails = 0
            # Update book snapshot texts
            self._apply_to_book(chunk)
        except TranslationError as e:
            chunk.status = ChunkStatus.FAILED
            chunk.error_message = str(e)
            if e.retryable and "Connection" in str(e):
                self._consecutive_conn_fails += 1
            else:
                self._consecutive_conn_fails = 0
            logger.warning("Chunk %s failed: %s", chunk.chunk_id, e)
        finally:
            chunk.updated_at = datetime.now(timezone.utc).isoformat()
            self.storage.update_chunk(self.job.job_id, chunk)
            all_c = self.storage.load_chunks(self.job.job_id)
            completed = sum(1 for c in all_c if c.status == ChunkStatus.COMPLETED)
            failed = sum(1 for c in all_c if c.status == ChunkStatus.FAILED)
            self.storage.update_job_progress(self.job.job_id, completed, failed)
            self._emit(
                "chunk_done",
                {
                    "chunk_id": chunk.chunk_id,
                    "status": chunk.status.value,
                    "completed": completed,
                    "failed": failed,
                    "total": len(all_c),
                },
            )

    def _apply_to_book(self, chunk: Chunk) -> None:
        """Write translated text back into the in-memory job.book snapshot."""
        for ch in self.job.book.chapters:
            if ch.id != chunk.chapter_id:
                continue
            new_blocks: list[ContentBlock] = []
            for b in ch.blocks:
                if b.id in chunk.translated_texts:
                    new_blocks.append(b.with_text(chunk.translated_texts[b.id]))
                else:
                    new_blocks.append(b)
            ch.blocks = new_blocks
        # Persist book snapshot
        book_id = getattr(self.job, "_book_id", self.job.job_id)
        self.storage.save_book(self.job.book, book_id=book_id)

    def _emit(self, event: str, data: dict) -> None:
        if self.on_progress:
            try:
                self.on_progress(event, data)
            except Exception:
                logger.exception("progress callback error")

    def apply_all_translations_to_book(self) -> CanonicalBook:
        """Rebuild book texts from all completed chunks (for export)."""
        chunks = self.storage.load_chunks(self.job.job_id)
        id_to_text: dict[str, str] = {}
        for c in chunks:
            if c.status == ChunkStatus.COMPLETED:
                id_to_text.update(c.translated_texts)
        for ch in self.job.book.chapters:
            ch.blocks = [
                b.with_text(id_to_text[b.id]) if b.id in id_to_text else b
                for b in ch.blocks
            ]
        return self.job.book
