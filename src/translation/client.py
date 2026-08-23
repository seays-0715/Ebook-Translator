"""OpenAI-compatible Local AI client.

Does not hard-code HYMT; any OpenAI-compatible endpoint works.
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.models.job import JobConfig


class TranslationError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class TranslationClient:
    def __init__(self, config: JobConfig) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.endpoint.rstrip("/") + "/"
            if not config.endpoint.endswith("/v1")
            else config.endpoint,
            api_key="local",  # Local AI typically ignores key
            timeout=config.request_timeout_seconds,
        )
        # Normalize base_url: openai lib expects .../v1
        if not str(self._client.base_url).rstrip("/").endswith("v1"):
            self._client = OpenAI(
                base_url=config.endpoint.rstrip("/") + "/v1",
                api_key="local",
                timeout=config.request_timeout_seconds,
            )

    def translate_chunk(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict:
        """Send one chunk; return parsed JSON object. Raises TranslationError."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ]
        try:
            resp = self._client.chat.completions.create(
                model=self.config.model_identifier or self.config.model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise TranslationError(
                f"Invalid JSON response: {e}", retryable=False
            ) from e
        except APITimeoutError as e:
            raise TranslationError(f"Timeout: {e}", retryable=True) from e
        except APIConnectionError as e:
            raise TranslationError(f"Connection error: {e}", retryable=True) from e
        except APIStatusError as e:
            code = e.status_code
            retryable = code >= 500 or code == 429
            raise TranslationError(
                f"API status {code}: {e}", retryable=retryable
            ) from e
        except Exception as e:
            raise TranslationError(str(e), retryable=False) from e

    def with_retry(self, fn, *, max_attempts: int | None = None):
        """Execute fn with retry for retryable errors only."""
        attempts = max_attempts or self.config.retry_count
        last: Exception | None = None
        for i in range(attempts):
            try:
                return fn()
            except TranslationError as e:
                last = e
                if not e.retryable or i == attempts - 1:
                    raise
                time.sleep(self.config.retry_delay_seconds * (i + 1))
        raise last  # type: ignore
