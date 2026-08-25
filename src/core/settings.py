"""Application settings (persisted JSON). Spec §42."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AIConnectionSettings(BaseModel):
    endpoint: str = "http://localhost:8000/v1"
    model: str = "local"
    model_identifier: str = ""
    api_key: str = "local"
    timeout_seconds: float = 120.0
    retry_count: int = 3
    retry_delay_seconds: float = 2.0
    request_interval_seconds: float = 0.5
    endpoint_fail_threshold: int = 3


class TranslationSettings(BaseModel):
    # Explicit selection only — no Auto Detect (registry default ja)
    source_language: str = "ja"
    target_language: str = "zh-Hant"
    # V1 styles: fiction | nonfiction
    style: str = "fiction"
    chunk_target_tokens: int = 1000
    carry_over_paragraphs: int = 2
    # Empty = use built-in default for the selected style
    prompt: str = ""
    # Per-style saved custom prompts (persist across restarts)
    fiction_prompt: str = ""
    nonfiction_prompt: str = ""


class OutputSettings(BaseModel):
    default_dir: str = ""
    same_as_input: bool = True
    after_completion: str = "nothing"  # nothing | sleep | shutdown | open_folder
    # clean | compact
    conversion_mode: str = "clean"


class AppSettings(BaseModel):
    schema_version: int = 1
    interface_language: str = ""  # empty = auto-detect
    ai: AIConnectionSettings = Field(default_factory=AIConnectionSettings)
    translation: TranslationSettings = Field(default_factory=TranslationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


def settings_path() -> Path:
    from src.core.paths import app_dir

    return app_dir() / "settings.json"


def load_settings(path: Path | None = None) -> AppSettings:
    p = path or settings_path()
    if not p.is_file():
        return AppSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return AppSettings.model_validate(data)
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(settings.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
