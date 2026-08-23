"""Level 1 — AI Response Validation (spec §32.1).

Checks:
- JSON valid (caller parses)
- Source IDs == Output IDs
- No duplicate IDs
- No empty translations
- No unexpected fields (lenient on extra keys)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    translations: dict[str, str] = field(default_factory=dict)


def validate_ai_response(
    source_ids: list[str],
    payload: dict,
) -> ValidationResult:
    errors: list[str] = []
    translations: dict[str, str] = {}

    if not isinstance(payload, dict):
        return ValidationResult(ok=False, errors=["Response is not a JSON object"])

    items = payload.get("translations")
    if not isinstance(items, list):
        return ValidationResult(
            ok=False, errors=["Missing or invalid 'translations' array"]
        )

    seen: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Item {i} is not an object")
            continue
        bid = item.get("id")
        text = item.get("text")
        if not bid or not isinstance(bid, str):
            errors.append(f"Item {i} missing valid 'id'")
            continue
        if bid in seen:
            errors.append(f"Duplicate id: {bid}")
            continue
        seen.add(bid)
        if text is None or (isinstance(text, str) and not text.strip()):
            errors.append(f"Empty translation for id: {bid}")
            continue
        if not isinstance(text, str):
            errors.append(f"Non-string text for id: {bid}")
            continue
        translations[bid] = text

    source_set = set(source_ids)
    out_set = set(translations.keys())
    missing = source_set - out_set
    extra = out_set - source_set
    if missing:
        errors.append(f"Missing ids: {sorted(missing)}")
    if extra:
        errors.append(f"Unknown ids: {sorted(extra)}")

    return ValidationResult(ok=len(errors) == 0, errors=errors, translations=translations)
