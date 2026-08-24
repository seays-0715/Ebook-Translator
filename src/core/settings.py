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
    source_language: str = "auto"
    target_language: str = "zh-TW"
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
    # preserve | clean | simplified
    conversion_mode: str = "clean"


class AppSettings(BaseModel):
    schema_version: int = 1
    interface_language: str = ""  # empty = auto-detect
    ai: AIConnectionSettings = Field(default_factory=AIConnectionSettings)
    translation: TranslationSettings = Field(default_factory=TranslationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    max_image_edge: int = 1600
    extra: dict[str, Any] = Field(default_factory=dict)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "AppSettings":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
