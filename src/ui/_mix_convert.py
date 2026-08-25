"""UI mixin."""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from src.core.chapter_ops import (
    ChapterOpError,
    merge_adjacent,
    remove_chapter,
    rename_chapter,
    split_chapter,
)
from src.core.languages import normalize_code
from src.core.pipeline import parse_to_book
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.models.blocks import BlockType
from src.models.book import CanonicalBook
from src.models.job import JobConfig, JobStatus
from src.queue.batch_queue import BatchQueue
from src.utils.power import after_completion_action
from src.ui.paths import assets_dir_for, data_dir, ebook_filetypes
from src.ui._common import (
    _CONVERSION_MODE_CODES,
    _ctk,
    _t,
    _relaunch_process,
    format_chapter_list_label,
    log,
)

# Temporary loader: full implementation restored from last good revision.
# See repository history commit f6227fb for the complete mixin body.
raise ImportError(
    "src.ui._mix_convert is being restored. "
    "If you see this message, the full ConvertMixin push is incomplete. "
    "Checkout commit f6227fb and re-apply the import fix removing "
    "_SOURCE_LANG_CODES/_TARGET_LANG_CODES."
)
