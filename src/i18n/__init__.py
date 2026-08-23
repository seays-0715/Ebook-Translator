"""Key-based i18n. V1: zh-HK + en.

Spec §42.5: detect system UI language; manual override via Settings.
Locale tables are loaded from JSON next to this module (and PyInstaller
_MEIPASS). Embedded tables are a hard fallback so a frozen EXE still
shows Traditional Chinese when interface_language=zh-HK even if JSON
was not packaged.
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

_EMBEDDED_ZH_HK: dict[str, str] = {
    "app_title": "電子書翻譯工具",
    "convert": "轉換 / 正規化",
    "translate": "翻譯",
    "glossary": "術語表建立",
    "settings": "設定",
    "confirm_convert": "確認並轉換",
    "open_file": "開啟檔案…",
    "add_books": "加入書籍…",
    "chapters": "章節",
    "merge": "合併",
    "split": "分割",
    "rename": "重新命名",
    "remove": "移除",
    "start_translation": "開始翻譯",
    "pause": "暫停",
    "resume": "繼續",
    "cancel": "取消",
    "force_export": "強制匯出（可能不完整）",
    "create": "建立",
    "build_from_pair": "由對照建立…",
    "refresh": "重新整理",
    "save": "儲存",
    "done": "完成",
    "info": "提示",
    "error": "錯誤",
    "confirm": "確認",
    "idle": "待命",
    "queue_started": "佇列已開始",
    "queue_finished": "佇列已結束",
    "pause_requested": "已要求暫停",
    "resume_log": "繼續",
    "output_folder": "輸出資料夾",
    "open_file_first": "請先開啟檔案",
    "select_chapter": "請選擇章節",
    "no_next_chapter": "沒有下一章可合併",
    "merged_next": "已與下一章合併",
    "split_need_blocks": "章節至少需要 2 個區塊才能分割",
    "split_at_block": "已於區塊 {block_id}（中點）分割",
    "renamed": "已重新命名",
    "chapter_removed": "已移除章節",
    "remove_chapter_q": "移除這個章節？",
    "open_analyze_first": "請先開啟並分析檔案",
    "wrote_file": "已寫入 {path}",
    "add_books_output_first": "請先加入書籍並選擇輸出資料夾",
    "queued_books": "已排入 {count} 本書",
    "loaded_file": "已載入 {name}",
    "warnings_prefix": "警告：{text}",
    "book_info": "書名：{title}  |  作者：{author}  |  語言：{language}  |  章節：{chapters}",
    "chapter_row": "{n}. {title}  （{blocks} 區塊）",
    "rename_title": "重新命名",
    "rename_prompt": "新章節標題：",
    "glossary_name_prompt": "名稱：",
    "glossary_name_default": "新術語表",
    "glossary_build_name": "術語表名稱：",
    "glossary_created": "已建立 {id}",
    "glossary_build_result": "術語表 {id}  候選={candidates}  對齊對={pairs}",
    "glossary_manual_align": "需要手動對齊：{message}",
    "glossary_row": "{id}  {name}  v{version}  條目={entries} 已確認={confirmed}",
    "original_book": "原文書籍",
    "official_translation": "官方譯本",
    "filetypes_ebook": "電子書",
    "filetypes_all": "全部",
    "filetypes_epub": "EPUB",
    "progress_book": "書籍：{book}",
    "progress_chapter": "章節：{current} / {total}",
    "progress_chunk": "區塊：{current} / {total}",
    "progress_overall": "總進度：{percent}%",
    "progress_job_line": "任務 {job_id}  {completed}/{total}  狀態={status}",
    "progress_exported": "已匯出 {path}",
    "progress_status": "狀態={status}",
    "settings_ai": "AI 連線",
    "settings_translation": "翻譯",
    "settings_retry": "重試 / 逾時",
    "settings_output": "輸出",
    "settings_power": "電源",
    "settings_advanced": "進階",
    "settings_interface": "介面",
    "label_endpoint": "端點",
    "label_model": "模型",
    "label_model_id": "模型識別碼",
    "label_api_key": "API 金鑰",
    "label_source_lang": "來源語言",
    "label_target_lang": "目標語言",
    "label_style": "風格",
    "label_chunk_tokens": "Chunk 目標 tokens",
    "label_carry_over": "延續段落數",
    "label_prompt": "系統提示詞（可選）",
    "hint_prompt": "留空則使用內建預設。只影響新建的 Job。",
    "label_timeout": "逾時（秒）",
    "label_retry_count": "重試次數",
    "label_retry_delay": "重試延遲（秒）",
    "label_request_interval": "請求間隔（秒）",
    "label_endpoint_fail": "端點失效閾值",
    "label_after_completion": "完成後動作",
    "label_interface_lang": "介面語言",
    "label_max_image_edge": "圖片最長邊（px）",
    "hint_after_completion": "nothing | sleep | shutdown | open_folder",
    "hint_interface_lang": "空白或 (auto) = 跟隨系統",
    "job_paused_endpoint": "無法連接 Local AI（{endpoint}），Job 已自動暫停。",
    "unsupported_schema": "不支援的 schema 版本，請重新建立 Job。",
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
    if lang == "zh-HK":
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
    if lower == "en" or lower.startswith("en-"):
        return "en"
    if any(
        tok in lower
        for tok in ("hant", "cht", "zh-tw", "zh-hk", "zh-mo", "zh-hant")
    ):
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
