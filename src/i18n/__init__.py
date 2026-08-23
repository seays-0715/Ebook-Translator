"""Key-based i18n. V1: zh-HK, zh-TW, en.

Spec §42.5: system detection; manual override via Settings.
JSON under this package / PyInstaller _MEIPASS; embedded tables as fallback.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path

_CACHE: dict[str, dict[str, str]] = {}
_CURRENT = "en"
_SUPPORTED = ("en", "zh-HK", "zh-TW")

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
    "restart_required": "Restart required",
    "restart_now": "Restart Now",
    "restart_later": "Later",
    "restart_prompt": "Interface language will apply after restart. Restart now?",
    "lang_zh_hk": "Traditional Chinese (Hong Kong)",
    "lang_zh_tw": "Traditional Chinese (Taiwan)",
    "lang_en": "English",
    "lang_auto": "System default",
    "style_auto": "Auto Detect",
    "style_natural": "Natural",
    "style_faithful": "Faithful",
    "style_literary": "Literary",
    "style_light_novel": "Light Novel",
    "style_custom": "Custom",
    "after_nothing": "Do Nothing",
    "after_sleep": "Sleep",
    "after_shutdown": "Shutdown",
    "after_open_folder": "Open Output Folder",
    "src_auto": "Auto Detect",
    "error_open_file": "Could not open file: {detail}",
    "error_analyze": "Analysis failed: {detail}",
    "drop_hint": "Drop EPUB/TXT here, or use Open File",
    "settings_saved": "Settings saved.",
    "send_to_translate": "Send to Translate",
    "chapter_detection": "Chapter Detection",
    "chapter_row_compact": "{n}. {title}  ({blocks})",
    "label_title": "Title",
    "label_author": "Author",
    "label_language": "Language",
    "label_chapter_count": "Chapters",
    "label_image_count": "Images",
    "queued_normalized": "Queued normalized book: {title}",
    "queue_items": "Queue",
    "remove_job_delete_data_q": "Also delete translation checkpoints for this job?",
    "glossary_list": "Glossaries",
    "glossary_candidates": "Candidates / Entries",
    "select_glossary_first": "Select a glossary first",
    "import": "Import…",
    "export": "Export…",
    "edit": "Edit",
    "reject": "Reject",
}

_EMBEDDED_ZH_HK: dict[str, str] = {
    "app_title": "\u96fb\u5b50\u66f8\u7ffb\u8b6f\u5de5\u5177",
    "convert": "\u8f49\u63db / \u6b63\u898f\u5316",
    "translate": "\u7ffb\u8b6f",
    "glossary": "\u8853\u8a9e\u8868\u5efa\u7acb",
    "settings": "\u8a2d\u5b9a",
    "confirm_convert": "\u78ba\u8a8d\u4e26\u8f49\u63db",
    "open_file": "\u958b\u555f\u6a94\u6848\u2026",
    "add_books": "\u52a0\u5165\u66f8\u7c4d\u2026",
    "chapters": "\u7ae0\u7bc0",
    "merge": "\u5408\u4f75",
    "split": "\u5206\u5272",
    "rename": "\u91cd\u65b0\u547d\u540d",
    "remove": "\u79fb\u9664",
    "start_translation": "\u958b\u59cb\u7ffb\u8b6f",
    "pause": "\u66ab\u505c",
    "resume": "\u7e7c\u7e8c",
    "cancel": "\u53d6\u6d88",
    "force_export": "\u5f37\u5236\u532f\u51fa\uff08\u53ef\u80fd\u4e0d\u5b8c\u6574\uff09",
    "create": "\u5efa\u7acb",
    "build_from_pair": "\u7531\u5c0d\u7167\u5efa\u7acb\u2026",
    "refresh": "\u91cd\u65b0\u6574\u7406",
    "save": "\u5132\u5b58",
    "done": "\u5b8c\u6210",
    "info": "\u63d0\u793a",
    "error": "\u932f\u8aa4",
    "confirm": "\u78ba\u8a8d",
    "idle": "\u5f85\u547d",
    "queue_started": "\u4f47\u5217\u5df2\u958b\u59cb",
    "queue_finished": "\u4f47\u5217\u5df2\u7d50\u675f",
    "pause_requested": "\u5df2\u8981\u6c42\u66ab\u505c",
    "resume_log": "\u7e7c\u7e8c",
    "output_folder": "\u8f38\u51fa\u8cc7\u6599\u593e",
    "open_file_first": "\u8acb\u5148\u958b\u555f\u6a94\u6848",
    "select_chapter": "\u8acb\u9078\u64c7\u7ae0\u7bc0",
    "no_next_chapter": "\u6c92\u6709\u4e0b\u4e00\u7ae0\u53ef\u5408\u4f75",
    "merged_next": "\u5df2\u8207\u4e0b\u4e00\u7ae0\u5408\u4f75",
    "split_need_blocks": "\u7ae0\u7bc0\u81f3\u5c11\u9700\u8981 2 \u500b\u5340\u584a\u624d\u80fd\u5206\u5272",
    "split_at_block": "\u5df2\u65bc\u5340\u584a {block_id}\uff08\u4e2d\u9ede\uff09\u5206\u5272",
    "renamed": "\u5df2\u91cd\u65b0\u547d\u540d",
    "chapter_removed": "\u5df2\u79fb\u9664\u7ae0\u7bc0",
    "remove_chapter_q": "\u79fb\u9664\u9019\u500b\u7ae0\u7bc0\uff1f",
    "open_analyze_first": "\u8acb\u5148\u958b\u555f\u4e26\u5206\u6790\u6a94\u6848",
    "wrote_file": "\u5df2\u5beb\u5165 {path}",
    "add_books_output_first": "\u8acb\u5148\u52a0\u5165\u66f8\u7c4d\u4e26\u9078\u64c7\u8f38\u51fa\u8cc7\u6599\u593e",
    "queued_books": "\u5df2\u6392\u5165 {count} \u672c\u66f8",
    "loaded_file": "\u5df2\u8f09\u5165 {name}",
    "warnings_prefix": "\u8b66\u544a\uff1a{text}",
    "book_info": "\u66f8\u540d\uff1a{title}  |  \u4f5c\u8005\uff1a{author}  |  \u8a9e\u8a00\uff1a{language}  |  \u7ae0\u7bc0\uff1a{chapters}",
    "chapter_row": "{n}. {title}  \uff08{blocks} \u5340\u584a\uff09",
    "rename_title": "\u91cd\u65b0\u547d\u540d",
    "rename_prompt": "\u65b0\u7ae0\u7bc0\u6a19\u984c\uff1a",
    "glossary_name_prompt": "\u540d\u7a31\uff1a",
    "glossary_name_default": "\u65b0\u8853\u8a9e\u8868",
    "glossary_build_name": "\u8853\u8a9e\u8868\u540d\u7a31\uff1a",
    "glossary_created": "\u5df2\u5efa\u7acb {id}",
    "glossary_build_result": "\u8853\u8a9e\u8868 {id}  \u5019\u9078={candidates}  \u5c0d\u9f4a\u5c0d={pairs}",
    "glossary_manual_align": "\u9700\u8981\u624b\u52d5\u5c0d\u9f4a\uff1a{message}",
    "glossary_row": "{id}  {name}  v{version}  \u689d\u76ee={entries} \u5df2\u78ba\u8a8d={confirmed}",
    "original_book": "\u539f\u6587\u66f8\u7c4d",
    "official_translation": "\u5b98\u65b9\u8b6f\u672c",
    "filetypes_ebook": "\u96fb\u5b50\u66f8",
    "filetypes_all": "\u5168\u90e8",
    "filetypes_epub": "EPUB",
    "progress_book": "\u66f8\u7c4d\uff1a{book}",
    "progress_chapter": "\u7ae0\u7bc0\uff1a{current} / {total}",
    "progress_chunk": "\u5340\u584a\uff1a{current} / {total}",
    "progress_overall": "\u7e3d\u9032\u5ea6\uff1a{percent}%",
    "progress_job_line": "\u4efb\u52d9 {job_id}  {completed}/{total}  \u72c0\u614b={status}",
    "progress_exported": "\u5df2\u532f\u51fa {path}",
    "progress_status": "\u72c0\u614b={status}",
    "settings_ai": "AI \u9023\u7dda",
    "settings_translation": "\u7ffb\u8b6f",
    "settings_retry": "\u91cd\u8a66 / \u903e\u6642",
    "settings_output": "\u8f38\u51fa",
    "settings_power": "\u96fb\u6e90",
    "settings_advanced": "\u9032\u968e",
    "settings_interface": "\u4ecb\u9762",
    "label_endpoint": "\u7aef\u9ede",
    "label_model": "\u6a21\u578b",
    "label_model_id": "\u6a21\u578b\u8b58\u5225\u78bc",
    "label_api_key": "API \u91d1\u9470",
    "label_source_lang": "\u4f86\u6e90\u8a9e\u8a00",
    "label_target_lang": "\u76ee\u6a19\u8a9e\u8a00",
    "label_style": "\u98a8\u683c",
    "label_chunk_tokens": "Chunk \u76ee\u6a19 tokens",
    "label_carry_over": "\u5ef6\u7e8c\u6bb5\u843d\u6578",
    "label_prompt": "\u7cfb\u7d71\u63d0\u793a\u8a5e\uff08\u53ef\u9078\uff09",
    "hint_prompt": "\u7559\u7a7a\u5247\u4f7f\u7528\u5167\u5efa\u9810\u8a2d\u3002\u53ea\u5f71\u97ff\u65b0\u5efa\u7684 Job\u3002",
    "label_timeout": "\u903e\u6642\uff08\u79d2\uff09",
    "label_retry_count": "\u91cd\u8a66\u6b21\u6578",
    "label_retry_delay": "\u91cd\u8a66\u5ef6\u9072\uff08\u79d2\uff09",
    "label_request_interval": "\u8acb\u6c42\u9593\u9694\uff08\u79d2\uff09",
    "label_endpoint_fail": "\u7aef\u9ede\u5931\u6548\u95ef\u503c",
    "label_after_completion": "\u5b8c\u6210\u5f8c\u52d5\u4f5c",
    "label_interface_lang": "\u4ecb\u9762\u8a9e\u8a00",
    "label_max_image_edge": "\u5716\u7247\u6700\u9577\u908a\uff08px\uff09",
    "hint_after_completion": "nothing | sleep | shutdown | open_folder",
    "hint_interface_lang": "\u7a7a\u767d\u6216 (auto) = \u8ddf\u96a8\u7cfb\u7d71",
    "job_paused_endpoint": "\u7121\u6cd5\u9023\u63a5 Local AI\uff08{endpoint}\uff09\uff0cJob \u5df2\u81ea\u52d5\u66ab\u505c\u3002",
    "unsupported_schema": "\u4e0d\u652f\u63f4\u7684 schema \u7248\u672c\uff0c\u8acb\u91cd\u65b0\u5efa\u7acb Job\u3002",
    "restart_required": "\u9700\u8981\u91cd\u65b0\u555f\u52d5",
    "restart_now": "\u7acb\u5373\u91cd\u555f",
    "restart_later": "\u7a0d\u5f8c",
    "restart_prompt": "\u4ecb\u9762\u8a9e\u8a00\u5c07\u5728\u91cd\u65b0\u555f\u52d5\u5f8c\u751f\u6548\u3002\u8981\u7acb\u5373\u91cd\u555f\u55ce\uff1f",
    "lang_zh_hk": "\u7e41\u9ad4\u4e2d\u6587\uff08\u9999\u6e2f\uff09",
    "lang_zh_tw": "\u7e41\u9ad4\u4e2d\u6587\uff08\u53f0\u7063\uff09",
    "lang_en": "English",
    "lang_auto": "\u8ddf\u96a8\u7cfb\u7d71",
    "style_auto": "\u81ea\u52d5\u5075\u6e2c",
    "style_natural": "\u81ea\u7136",
    "style_faithful": "\u5fe0\u5be6",
    "style_literary": "\u6587\u5b78",
    "style_light_novel": "\u8f15\u5c0f\u8aaa",
    "style_custom": "\u81ea\u8a02",
    "after_nothing": "\u4e0d\u57f7\u884c\u52d5\u4f5c",
    "after_sleep": "\u7761\u7720",
    "after_shutdown": "\u95dc\u6a5f",
    "after_open_folder": "\u958b\u555f\u8f38\u51fa\u8cc7\u6599\u593e",
    "src_auto": "\u81ea\u52d5\u5075\u6e2c",
    "error_open_file": "\u7121\u6cd5\u958b\u555f\u6a94\u6848\uff1a{detail}",
    "error_analyze": "\u5206\u6790\u5931\u6557\uff1a{detail}",
    "drop_hint": "\u5c07 EPUB/TXT \u62d6\u653e\u5230\u6b64\u8655\uff0c\u6216\u4f7f\u7528\u300c\u958b\u555f\u6a94\u6848\u300d",
    "settings_saved": "\u8a2d\u5b9a\u5df2\u5132\u5b58\u3002",
    "send_to_translate": "\u9001\u53bb\u7ffb\u8b6f",
    "chapter_detection": "\u7ae0\u7bc0\u5075\u6e2c",
    "chapter_row_compact": "{n}. {title}  \uff08{blocks}\uff09",
    "label_title": "\u66f8\u540d",
    "label_author": "\u4f5c\u8005",
    "label_language": "\u8a9e\u8a00",
    "label_chapter_count": "\u7ae0\u7bc0\u6578",
    "label_image_count": "\u5716\u7247\u6578",
    "queued_normalized": "\u5df2\u6392\u5165\u6b63\u898f\u5316\u66f8\u7c4d\uff1a{title}",
    "queue_items": "\u4f47\u5217",
    "remove_job_delete_data_q": "\u540c\u6642\u522a\u9664\u6b64\u4efb\u52d9\u7684\u7ffb\u8b6f\u6aa2\u67e5\u9ede\uff1f",
    "glossary_list": "\u8853\u8a9e\u8868",
    "glossary_candidates": "\u5019\u9078 / \u689d\u76ee",
    "select_glossary_first": "\u8acb\u5148\u9078\u64c7\u8853\u8a9e\u8868",
    "import": "\u532f\u5165\u2026",
    "export": "\u532f\u51fa\u2026",
    "edit": "\u7de8\u8f2f",
    "reject": "\u62d2\u7d55",
}


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        dirs.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        dirs.append(base / "src" / "i18n")
        dirs.append(base / "i18n")
        dirs.append(base)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir / "src" / "i18n")
        dirs.append(exe_dir / "i18n")
        dirs.append(exe_dir)
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
    # zh-TW falls back to zh-HK file if dedicated file missing
    if lang == "zh-TW":
        names.append("zh-HK.json")
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


def _embedded(lang: str) -> dict[str, str]:
    if lang in ("zh-HK", "zh-TW"):
        return dict(_EMBEDDED_ZH_HK)
    return dict(_EMBEDDED_EN)


def _load(lang: str) -> dict[str, str]:
    if lang in _CACHE:
        return _CACHE[lang]
    data = _load_file(lang)
    if not data:
        data = _embedded(lang)
    _CACHE[lang] = data
    return data


def _normalize_to_ui_lang(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("_", "-")
    if not s:
        return None
    lower = s.lower()
    if lower in ("", "auto", "(auto)"):
        return None
    if lower == "en" or lower.startswith("en-"):
        return "en"
    if lower in ("zh-tw", "zh-hant-tw") or "zh-tw" in lower:
        return "zh-TW"
    if lower in ("zh-hk", "zh-hant-hk", "zh-mo") or "zh-hk" in lower:
        return "zh-HK"
    if any(tok in lower for tok in ("hant", "cht", "zh-hant")):
        return "zh-HK"
    if lower == "zh" or lower.startswith("zh-") or lower.startswith("chi"):
        return "zh-HK"
    if lower in _SUPPORTED:
        return lower
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
            if sub == 0x01:  # Traditional Taiwan
                return "zh-TW"
            if sub in (0x03, 0x05):  # HK / Macau
                return "zh-HK"
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
    if text is None and _CURRENT != "en":
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
