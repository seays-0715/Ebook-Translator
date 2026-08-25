"""Batch Queue — wraps Translation Job pipeline (spec §4).

Queue status and Job status are independent:
  Queue: Running | Paused | Stopped
  Job:   Pending | Processing | Paused | Completed | Completed with Errors | Cancelled

Only one book processes at a time. On job completion (or Completed with Errors),
auto-start next. Endpoint-level failure pauses the whole Queue.

JobStatus lifecycle (enforced by this module):

  PENDING → PROCESSING | CANCELLED
  PROCESSING → PAUSED | COMPLETED | COMPLETED_WITH_ERRORS | CANCELLED
  PAUSED → PENDING (resume) | CANCELLED
  COMPLETED → removable
  COMPLETED_WITH_ERRORS → PENDING (retry) | removable
  CANCELLED → removable

PROCESSING jobs cannot be removed. Pause/cancel of PROCESSING request stop via
TranslationEngine; the engine return value is the single owner of final status.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import uuid4

from src.core.pipeline import create_translation_job, export_job_epub
from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus, QueueStatus
from src.translation.engine import TranslationEngine

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, dict], None]


class QueueError(RuntimeError):
    """Domain error for illegal queue operations."""


@dataclass
class QueueItem:
    item_id: str
    source_path: str
    output_path: str
    job_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    error: str | None = None
    priority: int = 0
    book: object | None = None
    display_name: str = ""


@dataclass
class BatchQueue:
    storage: Storage
    work_root: Path
    config: JobConfig
    glossary: list[dict[str, str]] = field(default_factory=list)
    on_progress: ProgressCallback | None = None
    conversion_mode: str = "standard"

    def __post_init__(self) -> None:
        self.work_root = Path(self.work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._items: list[QueueItem] = []
        self._status = QueueStatus.STOPPED
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._current_engine: TranslationEngine | None = None
        self._current_item_id: str | None = None
        self._stop_flag = False
        self._pause_flag = False

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
            self._items.sort(key=lambda x: (x.priority, x.item_id))
            return item

    def remove(self, item_id: str, delete_job_data: bool = False) -> None:
        """Remove an item, deleting persistent job data first when requested."""
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if item is None:
                return
            if item.status == JobStatus.PROCESSING:
                raise QueueError(f"cannot remove job while PROCESSING: {item_id}")
            job_id = item.job_id if delete_job_data else None

            if job_id:
                self.storage.delete_job(job_id)

            self._items = [i for i in self._items if i.item_id != item_id]

    def cancel_job(self, item_id: str) -> None:
        """Alias used by UI / tests."""
        self.cancel(item_id)

    def cancel(self, item_id: str) -> None:
        """Cancel a PENDING, PAUSED, or PROCESSING job.

        PROCESSING: request_stop on the current engine; final CANCELLED is
        owned by engine.run() return value in _process_item.
        """
        engine_to_stop: TranslationEngine | None = None
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if item is None:
                raise QueueError(f"unknown queue item: {item_id}")
            if item.status in (JobStatus.PENDING, JobStatus.PAUSED):
                if item.job_id:
                    self.storage.update_job_status(item.job_id, JobStatus.CANCELLED)
                item.status = JobStatus.CANCELLED
                return
            if item.status == JobStatus.PROCESSING:
                if self._current_item_id != item_id or self._current_engine is None:
                    raise QueueError(
                        f"PROCESSING job has no active TranslationEngine: {item_id}"
                    )
                engine_to_stop = self._current_engine
            else:
                raise QueueError(
                    f"cannot cancel job in status {item.status}: {item_id}"
                )
        try:
            engine_to_stop.request_stop()
        except Exception:
            logger.exception("request_stop failed for %s", item_id)
            raise

    def pause_job(self, item_id: str) -> None:
        """Request pause of a PROCESSING job through its active engine."""
        engine_to_pause: TranslationEngine | None = None
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if item is None:
                raise QueueError(f"unknown queue item: {item_id}")
            if item.status == JobStatus.PAUSED:
                return
            if item.status != JobStatus.PROCESSING:
                raise QueueError(
                    f"pause_job only for PROCESSING, got {item.status}: {item_id}"
                )
            if self._current_item_id != item_id or self._current_engine is None:
                raise QueueError(
                    f"PROCESSING job has no active TranslationEngine: {item_id}"
                )
            engine_to_pause = self._current_engine
        try:
            engine_to_pause.request_pause()
        except Exception:
            logger.exception("request_pause failed for %s", item_id)
            raise

    def resume_job(self, item_id: str) -> None:
        """Resume only a PAUSED job back to PENDING."""
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if item is None:
                raise QueueError(f"unknown queue item: {item_id}")
            if item.status != JobStatus.PAUSED:
                raise QueueError(
                    f"resume_job only for PAUSED, got {item.status}: {item_id}"
                )
            if item.job_id:
                self.storage.update_job_status(item.job_id, JobStatus.PENDING)
            item.status = JobStatus.PENDING
            item.error = None

    def retry_job(self, item_id: str) -> None:
        """Re-queue a completed_with_errors job using the same frozen job_id."""
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if not item:
                raise QueueError(f"unknown queue item: {item_id}")
            if item.status != JobStatus.COMPLETED_WITH_ERRORS:
                raise QueueError(
                    f"retry_job only for completed_with_errors, got {item.status}"
                )
            if not item.job_id:
                raise QueueError("retry_job requires an existing job_id")
            self.storage.update_job_status(item.job_id, JobStatus.PENDING)
            item.status = JobStatus.PENDING
            item.error = None

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                if self._status == QueueStatus.PAUSED:
                    self._pause_flag = False
                    self._status = QueueStatus.RUNNING
                return
            self._stop_flag = False
            self._pause_flag = False
            self._status = QueueStatus.RUNNING
            self._worker = threading.Thread(target=self._run_loop, daemon=True)
            self._worker.start()

    def pause(self) -> None:
        """Pause the whole queue (not a single job)."""
        with self._lock:
            self._pause_flag = True
            self._status = QueueStatus.PAUSED
            if self._current_engine is not None:
                self._current_engine.request_pause()

    def resume(self) -> None:
        with self._lock:
            self._pause_flag = False
            if self._status == QueueStatus.PAUSED:
                self._status = QueueStatus.RUNNING
        if not self._worker or not self._worker.is_alive():
            self.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_flag = True
            self._pause_flag = False
            self._status = QueueStatus.STOPPED
            if self._current_engine is not None:
                self._current_engine.request_stop()

    def _next_pending(self) -> QueueItem | None:
        """Pick the next job eligible for automatic processing."""
        for i in self._items:
            if i.status == JobStatus.PENDING:
                return i
        return None

    def _run_loop(self) -> None:
        import time

        while True:
            with self._lock:
                if self._stop_flag or self._status == QueueStatus.STOPPED:
                    self._status = QueueStatus.STOPPED
                    return
                if self._pause_flag or self._status == QueueStatus.PAUSED:
                    self._status = QueueStatus.PAUSED
                    item = None
                else:
                    item = self._next_pending()
                    if item is None:
                        self._status = QueueStatus.STOPPED
                        return

            if item is None:
                time.sleep(0.2)
                continue

            self._process_item(item)

    def _process_item(self, item: QueueItem) -> None:
        with self._lock:
            if item.status != JobStatus.PENDING:
                return
            item.status = JobStatus.PROCESSING
            self._current_item_id = item.item_id

        try:
            if not item.job_id:
                stem = Path(item.source_path).stem if item.source_path else "book"
                work = self.work_root / stem / str(uuid4())[:8]
                job = create_translation_job(
                    item.source_path if not item.book else None,
                    self.storage,
                    self.config,
                    work_dir=work,
                    book=item.book,
                    glossary_entries=self.glossary,
                )
                item.job_id = job.job_id
            else:
                job = self.storage.load_job(item.job_id)
                if job is None:
                    raise RuntimeError(f"missing job {item.job_id}")

            def _cb(info: dict) -> None:
                try:
                    if self.on_progress:
                        self.on_progress(item.item_id, info)
                except Exception:
                    logger.exception("queue progress callback error")

            engine = TranslationEngine(self.storage, job, on_progress=_cb)
            with self._lock:
                self._current_engine = engine
            status = engine.run()
            with self._lock:
                self._current_engine = None
                self._current_item_id = None
                item.status = status
                if status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS):
                    try:
                        export_job_epub(
                            self.storage,
                            item.job_id,
                            item.output_path,
                            force=(status == JobStatus.COMPLETED_WITH_ERRORS),
                            conversion_mode=self.conversion_mode or "standard",
                        )
                    except Exception as ex:
                        logger.exception("export failed")
                        item.status = JobStatus.COMPLETED_WITH_ERRORS
                        item.error = f"export_failed: {ex}"
                elif status == JobStatus.PAUSED:
                    self._pause_flag = True
                    self._status = QueueStatus.PAUSED
        except Exception as e:
            logger.exception("queue item failed: %s", item.display_name)
            with self._lock:
                item.status = JobStatus.COMPLETED_WITH_ERRORS
                item.error = str(e)
                self._current_engine = None
                self._current_item_id = None
            if item.job_id:
                self.storage.update_job_status(
                    item.job_id, JobStatus.COMPLETED_WITH_ERRORS
                )
