"""Key-based i18n. V1: zh-HK + en. Fallback: embedded English, then key.

Spec §42.5: detect system UI language; manual override via Settings.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path

_CACHE: dict[str, dict[str, str]] = {}
_CURRENT = "en"
_SUPPORTED = ("en", "zh-HK")

# Minimal embedded English so UI never shows raw keys if JSON is missing
_EMBEDDED_EN: dict[str, str] = {
    "app_title": "Ebook Translator",
    "convert": "Convert / Normalize",
    "translate": "Translate",
    "glossary": "Glossary Builder",
    "settings": "Settings",
    "confirm_convert": "Confirm & Convert",
    "open_file": "Open File…",
    "add_books": "Add Books…",
    "chapters": "Chapters",
    "merge": "Merge",
    "split": "Split",
    "rename": "Rename",
    "remove": "Remove",
    "start_translation": "Start Translation",
    "pause": "Pause",
    "resume": "Resume",
    "cancel": "Cancel",
    "force_export": "Force Export (may be incomplete)",
    "create": "Create",
    "build_from_pair": "Build from pair…",
    "refresh": "Refresh",
    "save": "Save",
    "done": "Done",
    "info": "Info",
    "error": "Error",
    "confirm": "Confirm",
    "idle": "Idle",
    "queue_started": "Queue started",
    "queue_finished": "Queue finished",
    "pause_requested": "Pause requested",
    "resume_log": "Resume",
    "output_folder": "Output folder",
    "open_file_first": "Open a file first",
    "select_chapter": "Select a chapter",
    "no_next_chapter": "No next chapter to merge with",
    "merged_next": "Merged with next chapter",
    "split_need_blocks": "Chapter needs at least 2 blocks to split",
    "split_at_block": "Split at block {block_id} (midpoint)",
    "renamed": "Renamed",
    "chapter_removed": "Chapter removed",
    "remove_chapter_q": "Remove this chapter?",
    "open_analyze_first": "Open and analyze a file first",
    "wrote_file": "Wrote {path}",
    "add_books_output_first": "Add books and output folder first",
    "queued_books": "Queued {count} book(s)",
    "loaded_file": "Loaded {name}",
    "warnings_prefix": "Warnings: {text}",
    "book_info": "Title: {title}  |  Author: {author}  |  Lang: {language}  |  Chapters: {chapters}",
    "chapter_row": "{n}. {title}  ({blocks} blocks)",
    "rename_title": "Rename",
    "rename_prompt": "New chapter title:",
    "glossary_name_prompt": "Name:",
    "glossary_name_default": "New Glossary",
    "glossary_build_name": "Glossary name:",
    "glossary_created": "Created {id}",
    "glossary_build_result": "Glossary {id}  candidates={candidates}  pairs={pairs}",
    "glossary_manual_align": "MANUAL ALIGNMENT: {message}",
    "glossary_row": "{id}  {name}  v{version}  entries={entries} confirmed={confirmed}",
    "original_book": "Original book",
    "official_translation": "Official translation",
    "filetypes_ebook": "Ebook",
    "filetypes_all": "All",
    "filetypes_epub": "EPUB",
    "progress_book": "Book: {book}",
    "progress_chapter": "Chapter: {current} / {total}",
    "progress_chunk": "Chunk: {current} / {total}",
    "progress_overall": "Overall: {percent}%",
    "progress_job_line": "Job {job_id}  {completed}/{total}  status={status}",
    "progress_exported": "Exported {path}",
    "progress_status": "status={status}",
    "settings_ai": "AI Connection",
    "settings_translation": "Translation",
    "settings_retry": "Retry / Timeout",
    "settings_output": "Output",
    "settings_power": "Power",
    "settings_advanced": "Advanced",
    "settings_interface": "Interface",
    "label_endpoint": "Endpoint",
    "label_model": "Model",
    "label_model_id": "Model identifier",
    "label_api_key": "API key",
    "label_source_lang": "Source language",
    "label_target_lang": "Target language",
    "label_style": "Style",
    "label_chunk_tokens": "Chunk target tokens",
    "label_carry_over": "Carry-over paragraphs",
    "label_prompt": "System prompt (optional)",
    "hint_prompt": "Leave empty to use the built-in default. Applied to new jobs only.",
    "label_timeout": "Timeout (seconds)",
    "label_retry_count": "Retry count",
    "label_retry_delay": "Retry delay (seconds)",
    "label_request_interval": "Request interval (seconds)",
    "label_endpoint_fail": "Endpoint fail threshold",
    "label_after_completion": "After completion",
    "label_interface_lang": "Interface language",
    "label_max_image_edge": "Max image edge (px)",
    "hint_after_completion": "nothing | sleep | shutdown | open_folder",
    "hint_interface_lang": "empty or (auto) = system language",
    "job_paused_endpoint": "Cannot connect to Local AI ({endpoint}). Job auto-paused.",
    "unsupported_schema": "Unsupported schema version. Please recreate the job.",
}


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        dirs.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "src" / "i18n")
        dirs.append(Path(meipass) / "i18n")
    dirs.append(Path.cwd() / "src" / "i18n")
    dirs.append(Path.cwd() / "i18n")
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _load_file(lang: str) -> dict[str, str]:
    names = [f"{lang}.json"]
    if "-" in lang:
        names.append(f"{lang.split('-')[0]}.json")
    for d in _candidate_dirs():
        for name in names:
            path = d / name
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        return {str(k): str(v) for k, v in data.items()}
                except Exception:
                    continue
    return {}


def _load(lang: str) -> dict[str, str]:
    if lang in _CACHE:
        return _CACHE[lang]
    data = _load_file(lang)
    if not data and lang == "en":
        data = dict(_EMBEDDED_EN)
    elif not data and lang != "en":
        data = _load_file("en") or dict(_EMBEDDED_EN)
    _CACHE[lang] = data
    return data


def _normalize_to_ui_lang(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("_", "-")
    if not s:
        return None
    lower = s.lower()
    if lower == "en" or lower.startswith("en-"):
        return "en"
    if any(
        tok in lower
        for tok in ("hant", "cht", "zh-tw", "zh-hk", "zh-mo", "zh-hant")
    ):
        return "zh-HK"
    if lower == "zh" or lower.startswith("zh-") or lower.startswith("chi"):
        return "zh-HK"
    return None


def _windows_ui_language() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        buf = ctypes.create_unicode_buffer(85)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if kernel32.GetLocaleInfoW(lang_id, 0x5C, buf, 85):
            return buf.value
        primary = lang_id & 0x3FF
        if primary == 0x04:
            sub = (lang_id >> 10) & 0x3F
            if sub in (0x01, 0x03, 0x05):
                return "zh-Hant"
            if sub == 0x02:
                return "zh-Hans"
            return "zh-Hant"
        if primary == 0x09:
            return "en"
    except Exception:
        return None
    return None


def detect_system_language() -> str:
    candidates: list[str] = []
    win = _windows_ui_language()
    if win:
        candidates.append(win)
    for getter in (
        lambda: locale.getlocale()[0],
        lambda: locale.getdefaultlocale()[0],  # type: ignore[deprecated]
    ):
        try:
            v = getter()
            if v:
                candidates.append(v)
        except Exception:
            pass
    for key in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        v = os.environ.get(key)
        if v:
            candidates.append(v.split(":")[0].split(".")[0])
    for raw in candidates:
        mapped = _normalize_to_ui_lang(raw)
        if mapped:
            return mapped
    return "en"


def set_language(lang: str) -> None:
    global _CURRENT
    mapped = _normalize_to_ui_lang(lang)
    if mapped is None:
        mapped = lang if lang in _SUPPORTED else "en"
    if mapped not in _SUPPORTED:
        mapped = "en"
    _CURRENT = mapped
    _CACHE.pop(mapped, None)
    _load(mapped)


def current_language() -> str:
    return _CURRENT


def get(key: str, **kwargs) -> str:
    table = _load(_CURRENT)
    text = table.get(key)
    if text is None:
        text = _load("en").get(key)
    if text is None:
        text = _EMBEDDED_EN.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


set_language(detect_system_language())
