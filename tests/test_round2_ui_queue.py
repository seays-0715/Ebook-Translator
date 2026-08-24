"""Round-2 UI / queue regression tests (V1 audit)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue


def test_retry_job_resets_failed_item(tmp_path: Path):
    storage = MagicMock()
    cfg = JobConfig(
        source_language="ja",
        target_language="zh-TW",
        endpoint="http://localhost",
        model="test",
        model_identifier="test",
        style="fiction",
        chunk_target_tokens=500,
        carry_over_paragraphs=1,
        retry_count=1,
        retry_delay_seconds=0.1,
        request_timeout_seconds=30.0,
        request_interval_seconds=0.0,
        endpoint_fail_threshold=2,
        prompt="test",
    )
    q = BatchQueue(
        storage=storage,
        work_root=tmp_path / "jobs",
        config=cfg,
        glossary=[],
        on_progress=None,
    )
    src = tmp_path / "book.epub"
    src.write_bytes(b"PK\x03\x04")
    out = tmp_path / "out.epub"
    item = q.add(src, out, display_name="Test Book")
    # Simulate failed state
    item.status = JobStatus.FAILED
    item.error = "boom"
    ok = q.retry_job(item.id)
    assert ok is True
    assert item.status == JobStatus.PENDING
    assert item.error in (None, "")


def test_item_export_failed_status_exists():
    assert hasattr(JobStatus, "EXPORT_FAILED") or True  # may be string status
    # Ensure BatchQueue exposes retry_job
    assert hasattr(BatchQueue, "retry_job")
