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
    source_path: Path | None
    output_path: Path
    display_name: str = ""
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    error: str | None = None
    job_id: str | None = None
    order: int = 0
    book: object | None = None  # optional CanonicalBook snapshot


class BatchQueue:
    """In-order batch runner. One job at a time; supports pause/resume/cancel."""

    def __init__(
        self,
        storage: Storage,
        work_root: Path,
        config: JobConfig,
        *,
        on_progress: ProgressCallback | None = None,
        glossary_entries: list | None = None,
        conversion_mode: str = "clean",
    ) -> None:
        self.storage = storage
        self.work_root = Path(work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.on_progress = on_progress
        self.glossary_entries = glossary_entries or []
        self.conversion_mode = conversion_mode  # clean | compact
        self._items: list[QueueItem] = []
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._status = QueueStatus.IDLE
        self._stop_flag = False
        self._pause_flag = False

    @property
    def status(self) -> QueueStatus:
        return self._status

    @property
    def items(self) -> list[QueueItem]:
        with self._lock:
            return list(self._items)

    def add(
        self,
        source_path: Path | None,
        output_path: Path,
        *,
        display_name: str | None = None,
        book: object | None = None,
    ) -> QueueItem:
        item = QueueItem(
            item_id=uuid4().hex[:12],
            source_path=Path(source_path) if source_path else None,
            output_path=Path(output_path),
            display_name=display_name
            or (Path(source_path).name if source_path else "book"),
            order=len(self._items),
            book=book,
        )
        with self._lock:
            self._items.append(item)
        return item

    def remove(self, item_id: str) -> None:
        with self._lock:
            self._items = [i for i in self._items if i.item_id != item_id]
            for idx, i in enumerate(self._items):
                i.order = idx

    def reorder(self, item_ids: list[str]) -> None:
        with self._lock:
            by_id = {i.item_id: i for i in self._items}
            new_list = []
            for iid in item_ids:
                if iid in by_id:
                    new_list.append(by_id.pop(iid))
            new_list.extend(by_id.values())
            for idx, i in enumerate(new_list):
                i.order = idx
            self._items = new_list

    def clear_finished(self) -> None:
        with self._lock:
            self._items = [
                i
                for i in self._items
                if i.status
                not in (
                    JobStatus.COMPLETED,
                    JobStatus.COMPLETED_WITH_ERRORS,
                    JobStatus.CANCELLED,
                    JobStatus.FAILED,
                )
            ]
            for idx, i in enumerate(self._items):
                i.order = idx

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._pause_flag = False
                self._status = QueueStatus.RUNNING
                return
            self._stop_flag = False
            self._pause_flag = False
            self._status = QueueStatus.RUNNING
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def pause(self) -> None:
        self._pause_flag = True

    def resume(self) -> None:
        self._pause_flag = False
        with self._lock:
            if self._status == QueueStatus.PAUSED:
                self._status = QueueStatus.RUNNING
        if not self._thread or not self._thread.is_alive():
            self.start()

    def stop(self) -> None:
        self._stop_flag = True
        self._pause_flag = False

    def resume_job(self, item_id: str) -> None:
        """Resume a single paused/cancelled-pending job back to PENDING."""
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if not item:
                return
            if item.status in (JobStatus.PAUSED, JobStatus.CANCELLED):
                item.status = JobStatus.PENDING
                item.error = None
                if item.job_id:
                    try:
                        self.storage.update_job_status(item.job_id, JobStatus.PENDING)
                    except Exception:
                        pass

    def retry_job(self, item_id: str) -> None:
        """Re-queue a completed_with_errors job using the same frozen job_id.

        Does not re-parse the book, does not rebuild JobConfig from current Settings,
        and keeps the existing job snapshot so retry is deterministic.
        """
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if not item:
                raise RuntimeError(f"unknown queue item: {item_id}")
            if item.status != JobStatus.COMPLETED_WITH_ERRORS:
                raise RuntimeError(
                    f"retry_job only for completed_with_errors, got {item.status}"
                )
            if not item.job_id:
                raise RuntimeError("retry_job requires an existing job_id")
            item.status = JobStatus.PENDING
            item.error = None
            item.progress = 0.0
            try:
                self.storage.update_job_status(item.job_id, JobStatus.PENDING)
            except Exception:
                logger.exception("retry_job storage update")

    def cancel_item(self, item_id: str) -> None:
        with self._lock:
            item = next((i for i in self._items if i.item_id == item_id), None)
            if not item:
                return
            if item.status in (JobStatus.PENDING, JobStatus.PROCESSING):
                item.status = (
                    JobStatus.PAUSED
                    if item.status == JobStatus.PROCESSING
                    else JobStatus.CANCELLED
                )
                if item.status == JobStatus.CANCELLED:
                    item.error = "cancelled"
                if item.job_id:
                    try:
                        self.storage.update_job_status(
                            item.job_id,
                            JobStatus.CANCELLED
                            if item.status == JobStatus.CANCELLED
                            else JobStatus.PAUSED,
                        )
                    except Exception:
                        pass

    def _next_pending(self) -> QueueItem | None:
        """Pick the next job eligible for automatic processing.

        Only PENDING items are selected. PAUSED jobs require an explicit
        resume_job() (user-initiated pause is not auto-resumed).
        """
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
                item = self._next_pending()
                if item is None:
                    if not any(i.status == JobStatus.PROCESSING for i in self._items):
                        self._status = QueueStatus.IDLE
                        return

            if self._pause_flag:
                time.sleep(0.2)
                continue
            if item is None:
                time.sleep(0.15)
                continue
            self._process_item(item)

    def _process_item(self, item: QueueItem) -> None:
        with self._lock:
            item.status = JobStatus.PROCESSING

        if not item.job_id:
            stem = Path(item.source_path).stem if item.source_path else "book"
            work = self.work_root / stem / str(uuid4())[:8]
            job = create_translation_job(
                item.source_path if not item.book else None,
                self.storage,
                self.config,
                work_dir=work,
                book=item.book,
                glossary_entries=self.glossary_entries,
            )
            item.job_id = job.job_id
        else:
            job = self.storage.load_job(item.job_id)
            if job is None:
                with self._lock:
                    item.status = JobStatus.FAILED
                    item.error = f"missing job {item.job_id}"
                return

        def _cb(info: dict) -> None:
            try:
                frac = float(info.get("progress", 0.0))
                item.progress = max(0.0, min(1.0, frac))
                if self.on_progress:
                    self.on_progress(item.item_id, info)
            except Exception:
                logger.exception("queue progress callback error")

        try:
            engine = TranslationEngine(self.storage, job, on_progress=_cb)
            status = engine.run()
            with self._lock:
                item.status = status
                if status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS):
                    item.progress = 1.0
                    try:
                        export_job_epub(
                            self.storage,
                            item.job_id,
                            item.output_path,
                            force=(status == JobStatus.COMPLETED_WITH_ERRORS),
                            conversion_mode=self.conversion_mode or "clean",
                        )
                    except Exception as ex:
                        logger.exception("export failed")
                        item.status = JobStatus.COMPLETED_WITH_ERRORS
                        item.error = f"export_failed: {ex}"
                elif status == JobStatus.PAUSED:
                    self._pause_flag = True
                    self._status = QueueStatus.PAUSED
                elif status == JobStatus.FAILED:
                    item.error = getattr(job, "error", None) or "failed"
        except Exception as e:
            logger.exception("queue item failed: %s", item.display_name)
            with self._lock:
                item.status = JobStatus.FAILED
                item.error = str(e)
            if item.job_id:
                try:
                    self.storage.update_job_status(item.job_id, JobStatus.FAILED)
                except Exception:
                    pass
        finally:
            if self.on_progress:
                try:
                    self.on_progress(
                        item.item_id,
                        {
                            "status": str(item.status),
                            "progress": item.progress,
                            "error": item.error,
                        },
                    )
                except Exception:
                    logger.exception("queue progress callback error")
