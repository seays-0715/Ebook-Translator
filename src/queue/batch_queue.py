"""Batch Queue — wraps Translation Job pipeline (spec §4).

Queue status and Job status are independent:
  Queue: Running | Paused | Stopped
  Job:   Pending | Processing | Paused | Completed | Completed with Errors | Cancelled

Only one book processes at a time. On job completion (or Completed with Errors),
auto-start next. Endpoint-level failure pauses the whole Queue.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from src.core.pipeline import create_translation_job, export_job_epub
from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus, QueueStatus
from src.translation.engine import TranslationEngine

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, dict], None]


@dataclass
class QueueItem:
    item_id: str
    source_path: str
    output_path: str
    job_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    error: str | None = None
    priority: int = 0  # lower = higher priority; insertion order as tiebreak
    # Optional pre-normalized Canonical Book (Preview corrections). When set,
    # Job creation uses this snapshot and does not re-parse source_path.
    book: object | None = None
    display_name: str = ""


@dataclass
class BatchQueue:
    storage: Storage
    work_root: Path
    config: JobConfig
    glossary: list[dict[str, str]] = field(default_factory=list)
    on_progress: ProgressCallback | None = None
    # preserve | clean | simplified — passed through to EPUB export
    conversion_mode: str = "clean"

    def __post_init__(self) -> None:
        self.work_root = Path(self.work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._items: list[QueueItem] = []
        self._status = QueueStatus.STOPPED
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._current_engine: TranslationEngine | None = None
        self._stop_flag = False
        self._pause_flag = False

    # ------------------------------------------------------------------ public

    @property
    def status(self) -> QueueStatus:
        return self._status

    def items(self) -> list[QueueItem]:
        with self._lock:
            return list(self._items)

    def add(
        self,
        source: str | Path,
        output: str | Path,
        *,
        priority: int | None = None,
        book: object | None = None,
        display_name: str | None = None,
    ) -> QueueItem:
        source = Path(source)
        output = Path(output)
        with self._lock:
            prio = priority if priority is not None else len(self._items)
            item = QueueItem(
                item_id=str(uuid4()),
                source_path=str(source),
                output_path=str(output),
                priority=prio,
                book=book,
                display_name=display_name
                or (
                    getattr(getattr(book, "metadata", None), "title", None)
                    if book is not None
                    else None
                )
                or source.name,
            )
            self._items.append(item)
            self._sort()
            return item

    def remove(self, item_id: str, *, delete_job_data: bool = False) -> None:
        """Remove item from queue. Processing items must be cancelled first.
        delete_job_data=True permanently deletes job checkpoints from storage.
        Default keeps checkpoints on disk (user may re-queue later).
        """
        with self._lock:
            item = self._find(item_id)
            if item.status == JobStatus.PROCESSING:
                raise RuntimeError("Cannot remove a processing item; pause/cancel first")
            job_id = item.job_id
            self._items = [i for i in self._items if i.item_id != item_id]
        if delete_job_data and job_id:
            try:
                self.storage.delete_job(job_id)
            except Exception:
                logger.exception("Failed to delete job data for %s", job_id)

    def cancel_job(self, item_id: str) -> None:
        """Cancel a job: stop new requests; completed checkpoints remain."""
        with self._lock:
            item = self._find(item_id)
            eng = self._current_engine
            current_job = eng.job.job_id if eng else None
            if item.job_id and item.job_id == current_job and eng:
                eng.request_stop()
            if item.status in (
                JobStatus.PENDING,
                JobStatus.PROCESSING,
                JobStatus.PAUSED,
            ):
                item.status = JobStatus.CANCELLED
            if item.job_id:
                try:
                    self.storage.update_job_status(item.job_id, JobStatus.CANCELLED)
                except Exception:
                    logger.exception("status update failed for cancel %s", item.job_id)

    def resume_job(self, item_id: str) -> None:
        """Resume a single paused/cancelled-pending job back to PENDING."""
        with self._lock:
            item = self._find(item_id)
            if item.status in (JobStatus.PAUSED, JobStatus.CANCELLED):
                item.status = JobStatus.PENDING
                item.error = None
                if item.job_id:
                    try:
                        self.storage.update_job_status(item.job_id, JobStatus.PENDING)
                    except Exception:
                        pass

    def retry_job(self, item_id: str) -> None:
        """Retry a COMPLETED_WITH_ERRORS job using the same frozen Job config.

        Does not re-parse the book, does not rebuild JobConfig from current Settings,
        and does not replace glossary snapshot. Reuses item.job_id.
        """
        with self._lock:
            item = self._find(item_id)
            if item.status != JobStatus.COMPLETED_WITH_ERRORS:
                raise RuntimeError(
                    f"retry_job only for completed_with_errors, got {item.status}"
                )
            if not item.job_id:
                raise RuntimeError("retry_job requires an existing job_id")
            item.status = JobStatus.PENDING
            item.error = None
            try:
                self.storage.update_job_status(item.job_id, JobStatus.PENDING)
            except Exception:
                logger.exception("status update failed for retry %s", item.job_id)

    def reorder(self, ordered_item_ids: list[str]) -> None:
        with self._lock:
            by_id = {i.item_id: i for i in self._items}
            if set(ordered_item_ids) != set(by_id):
                raise ValueError("ordered_item_ids must match current queue items")
            for rank, iid in enumerate(ordered_item_ids):
                by_id[iid].priority = rank
            self._sort()

    def start(self) -> None:
        with self._lock:
            if self._status == QueueStatus.RUNNING:
                return
            self._stop_flag = False
            self._pause_flag = False
            self._status = QueueStatus.RUNNING
            self._worker = threading.Thread(target=self._run_loop, daemon=True)
            self._worker.start()

    def pause(self) -> None:
        """Pause entire queue. Current job finishes its in-flight request then pauses."""
        with self._lock:
            self._pause_flag = True
            self._status = QueueStatus.PAUSED
            eng = self._current_engine
        if eng:
            eng.request_pause()

    def resume(self) -> None:
        with self._lock:
            if self._status == QueueStatus.RUNNING:
                return
            self._pause_flag = False
            self._stop_flag = False
            self._status = QueueStatus.RUNNING
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run_loop, daemon=True)
                self._worker.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_flag = True
            self._status = QueueStatus.STOPPED
            eng = self._current_engine
        if eng:
            eng.request_stop()

    def pause_job(self, item_id: str) -> None:
        """Pause a single job; queue stays Running so other jobs can proceed later."""
        with self._lock:
            item = self._find(item_id)
            eng = self._current_engine
            current_job = eng.job.job_id if eng else None
            if item.job_id and item.job_id == current_job and eng:
                eng.request_pause()
            elif item.status in (JobStatus.PENDING, JobStatus.PROCESSING):
                item.status = JobStatus.PAUSED

    # ------------------------------------------------------------------ internal

    def _find(self, item_id: str) -> QueueItem:
        for i in self._items:
            if i.item_id == item_id:
                return i
        raise KeyError(item_id)

    def _sort(self) -> None:
        self._items.sort(key=lambda x: x.priority)

    def _next_pending(self) -> QueueItem | None:
        for i in self._items:
            if i.status in (JobStatus.PENDING, JobStatus.PAUSED):
                # Skip user-paused individual jobs when only resuming queue?
                # Spec: if user pauses single job, queue still running, others continue.
                if i.status == JobStatus.PAUSED:
                    # Only pick up if we don't treat PAUSED as "user held"
                    # For simplicity: PENDING only for auto-advance; PAUSED needs explicit resume
                    continue
                return i
        return None

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if self._stop_flag or self._status == QueueStatus.STOPPED:
                    self._status = QueueStatus.STOPPED
                    break
                if self._pause_flag or self._status == QueueStatus.PAUSED:
                    self._status = QueueStatus.PAUSED
                    break
                item = self._next_pending()
                if item is None:
                    self._status = QueueStatus.STOPPED
                    break
            try:
                self._process_item(item)
            except Exception as e:
                logger.exception("Queue item failed: %s", item.item_id)
                with self._lock:
                    item.status = JobStatus.COMPLETED_WITH_ERRORS
                    item.error = str(e)
                self._emit("item_error", {"item_id": item.item_id, "error": str(e)})
                # Continue to next book (spec: do not block queue)
                continue

    def _process_item(self, item: QueueItem) -> None:
        with self._lock:
            item.status = JobStatus.PROCESSING

        # Create job if needed — freeze queue glossary into job config snapshot.
        # Prefer normalized book from Preview; do not re-parse source in that case.
        if not item.job_id:
            stem = Path(item.source_path).stem if item.source_path else "book"
            work = self.work_root / stem / str(uuid4())[:8]
            job = create_translation_job(
                item.source_path if not item.book else None,
                self.storage,
                self.config,
                work_dir=work,
                book=item.book,
                glossary_entries=list(self.glossary) if self.glossary else None,
            )
            with self._lock:
                item.job_id = job.job_id
                # Drop live book reference after snapshot is frozen into Job
                item.book = None
        else:
            # Resume: load job snapshot; do not re-inject current queue glossary
            job = self.storage.load_job(item.job_id)

        object.__setattr__(job, "_book_id", job.job_id)

        def progress(event: str, data: dict) -> None:
            data = {**data, "item_id": item.item_id, "job_id": item.job_id}
            self._emit(event, data)

        engine = TranslationEngine(
            self.storage,
            job,
            on_progress=progress,
        )
        with self._lock:
            self._current_engine = engine

        try:
            status = engine.run()
            with self._lock:
                item.status = status
                if status == JobStatus.PAUSED:
                    self._pause_flag = True
                    self._status = QueueStatus.PAUSED
                    # Endpoint failure message already on job
                    if job.error_summary and "Local AI" in (job.error_summary or ""):
                        # Spec §29.1: pause whole queue
                        pass

            if status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS):
                try:
                    export_job_epub(
                        self.storage,
                        item.job_id,
                        item.output_path,
                        conversion_mode=self.conversion_mode or "clean",
                    )
                    self._emit(
                        "item_exported",
                        {"item_id": item.item_id, "output": item.output_path},
                    )
                except Exception as e:
                    logger.warning("Export failed for %s: %s", item.item_id, e)
                    with self._lock:
                        item.error = f"export_failed: {e}"
                        if item.status == JobStatus.COMPLETED:
                            item.status = JobStatus.COMPLETED_WITH_ERRORS
                    self._emit(
                        "item_export_failed",
                        {
                            "item_id": item.item_id,
                            "output": item.output_path,
                            "error": str(e),
                        },
                    )
        finally:
            with self._lock:
                self._current_engine = None

    def emit(self, event: str, data: dict) -> None:
        self._emit(event, data)

    def _emit(self, event: str, data: dict) -> None:
        if self.on_progress:
            try:
                self.on_progress(event, data)
            except Exception:
                logger.exception("queue progress callback error")
