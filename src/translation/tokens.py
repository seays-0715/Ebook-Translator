"""Token counting: exact tokenizer when available, else heuristic (spec §20.2)."""

from __future__ import annotations

_enc = None
_enc_failed = False


def _get_encoder():
    global _enc, _enc_failed
    if _enc is not None or _enc_failed:
        return _enc
    try:
        import tiktoken

        # cl100k_base is a reasonable default for many OpenAI-compatible models
        _enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _enc_failed = True
        _enc = None
    return _enc


def count_tokens(text: str, *, model_hint: str | None = None) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(
        1
        for c in text
        if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff"
    )
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))
