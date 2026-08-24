"""Batch Queue — wraps Translation Job pipeline (spec §4).

Queue status and Job status are independent:
  Queue: Running | Paused | Stopped
  Job:   Pending | Processing | Paused | Completed | Completed with Errors | Cancelled
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from src.core.pipeline import create_translation_job, export_job_epub
from src.core.storage import Storage
from src.models.job import JobConfig, JobStatus
from src.translation.engine import TranslationEngine

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    item_id: str
    source_path: Path
    output_path: Path
    display_name: str = ""
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    error: Optional[str] = None
    job_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class BatchQueue:
    def __init__(
        self,
        storage: Storage,
        work_root: Path,
        config: JobConfig,
        engine: Optional[TranslationEngine] = None,
        on_progress: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.storage = storage
        self.work_root = Path(work_root)
        self.config = config
        self.engine = engine
        self.on_progress = on_progress
        self._items: dict[str, QueueItem] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._pause.set()  # not paused
        self._running = False

    def add(
        self,
        source_path: Path,
        output_path: Path,
        display_name: str = "",
    ) -> QueueItem:
        item = QueueItem(
            item_id=uuid4().hex[:12],
            source_path=Path(source_path),
            output_path=Path(output_path),
            display_name=display_name or Path(source_path).name,
        )
        with self._lock:
            self._items[item.item_id] = item
            self._order.append(item.item_id)
        return item

    def list_items(self) -> list[QueueItem]:
        with self._lock:
            return [self._items[i] for i in self._order if i in self._items]

    def remove(self, item_id: str) -> None:
        with self._lock:
            self._items.pop(item_id, None)
            if item_id in self._order:
                self._order.remove(item_id)

    def clear_completed(self) -> None:
        with self._lock:
            done = [
                i
                for i, it in self._items.items()
                if it.status
                in (
                    JobStatus.COMPLETED,
                    JobStatus.COMPLETED_WITH_ERRORS,
                    JobStatus.CANCELLED,
                )
            ]
            for i in done:
                self._items.pop(i, None)
                if i in self._order:
                    self._order.remove(i)

    def retry_job(self, item_id: str) -> None:
        """Retry a COMPLETED_WITH_ERRORS job using the same frozen Job config.

        Resets status to PENDING and clears error; keeps job_id so the engine
        reuses the frozen JobConfig snapshot (source/target/style/glossary).
        """
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                raise KeyError(item_id)
            if item.status != JobStatus.COMPLETED_WITH_ERRORS:
                raise RuntimeError(
                    f"retry_job only for completed_with_errors, got {item.status}"
                )
            if not item.job_id:
                raise RuntimeError("retry_job requires an existing job_id")
            item.status = JobStatus.PENDING
            item.error = None
            item.progress = 0.0
        self._emit("item_retry", {"item_id": item_id, "job_id": item.job_id})

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._pause.set()
            self._running = True
            self._worker = threading.Thread(target=self._run_loop, daemon=True)
            self._worker.start()

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    def stop(self) -> None:
        self._stop.set()
        self._pause.set()
        with self._lock:
            self._running = False

    def _run_loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._pause.wait(timeout=0.5)
                if self._stop.is_set():
                    break
                item = self._next_pending()
                if not item:
                    time.sleep(0.3)
                    continue
                self._process_item(item)
        finally:
            with self._lock:
                self._running = False

    def _next_pending(self) -> Optional[QueueItem]:
        with self._lock:
            for iid in self._order:
                it = self._items.get(iid)
                if it and it.status == JobStatus.PENDING:
                    return it
        return None

    def _process_item(self, item: QueueItem) -> None:
        item.status = JobStatus.PROCESSING
        self._emit("item_start", {"item_id": item.item_id})
        try:
            # Create or reuse job with frozen config
            if item.job_id:
                job = self.storage.load_job(item.job_id)
                if job is None:
                    job = create_translation_job(
                        source_path=item.source_path,
                        output_path=item.output_path,
                        config=self.config,
                        storage=self.storage,
                        work_root=self.work_root,
                    )
                    item.job_id = job.job_id
            else:
                job = create_translation_job(
                    source_path=item.source_path,
                    output_path=item.output_path,
                    config=self.config,
                    storage=self.storage,
                    work_root=self.work_root,
                )
                item.job_id = job.job_id

            if not self.engine:
                raise RuntimeError("No translation engine configured")

            def _progress(pct: float, msg: str = "") -> None:
                item.progress = pct
                self._emit(
                    "item_progress",
                    {"item_id": item.item_id, "progress": pct, "message": msg},
                )

            status = self.engine.run_job(job, on_progress=_progress)
            item.status = status
            if status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS):
                try:
                    export_job_epub(job, item.output_path, storage=self.storage)
                    self._emit(
                        "item_done",
                        {
                            "item_id": item.item_id,
                            "output": str(item.output_path),
                            "status": status.value,
                        },
                    )
                except Exception as ex:
                    logger.exception("export failed for %s", item.item_id)
                    item.error = f"export_failed: {ex}"
                    item.status = JobStatus.COMPLETED_WITH_ERRORS
                    self._emit(
                        "item_export_failed",
                        {
                            "item_id": item.item_id,
                            "error": str(ex),
                            "output": str(item.output_path),
                        },
                    )
            elif status == JobStatus.CANCELLED:
                self._emit("item_cancelled", {"item_id": item.item_id})
            else:
                self._emit(
                    "item_failed",
                    {"item_id": item.item_id, "status": status.value},
                )
        except Exception as ex:
            logger.exception("queue item failed: %s", item.item_id)
            item.status = JobStatus.COMPLETED_WITH_ERRORS
            item.error = str(ex)
            self._emit(
                "item_failed",
                {"item_id": item.item_id, "error": str(ex)},
            )

    def _emit(self, event: str, data: dict) -> None:
        if self.on_progress:
            try:
                self.on_progress(event, data)
            except Exception:
                logger.exception("queue progress callback error")
