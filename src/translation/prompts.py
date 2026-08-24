"""Default translation prompts with template variables."""

from __future__ import annotations

from src.core.languages import code_to_name, normalize_code

# Template variables supported in prompts (editor shows the template):
#   {{source_language}} / {{source_language_name}}
#   {{target_language}} / {{target_language_name}}
#   {{text}}  (when single-text style is used; block payload uses JSON)
#
# At request time the application renders these from the frozen Job config.
# Do not hard-code language pairs inside the default prompts.

DEFAULT_SYSTEM_PROMPT = """You are a professional book translator.
Translate the given content blocks from {{source_language_name}} to {{target_language_name}}.

Rules:
1. Return ONLY a JSON object of the form:
   {"translations": [{"id": "<block_id>", "text": "<translated text>"}, ...]}
2. Every source id must appear exactly once in the output. No missing, no extra, no duplicate ids.
3. Do not translate or alter block ids.
4. If a block is already in the target language, output it unchanged — do not polish or rewrite.
5. Preserve tone and meaning. Apply the requested style.
6. Use the provided glossary terms when applicable (respect inflection / honorifics but keep the specified root translation).
7. Carry-over context (previous chunk tail source + translation) is for reference only —
   do NOT translate those blocks; only translate the "to_translate" list.
"""

FICTION_DEFAULT_PROMPT = """You are a professional literary translator for fiction (including light novels and dialogue-heavy works).
Translate content blocks from {{source_language_name}} to {{target_language_name}}.

Rules:
1. Return ONLY JSON: {"translations": [{"id": "<block_id>", "text": "<translated text>"}, ...]}
2. Every source id must appear exactly once. No missing, extra, or duplicate ids.
3. Do not alter block ids.
4. Prefer natural, fluent prose that preserves character voice and dialogue tone.
5. Keep narrative rhythm; handle onomatopoeia and interjections sensibly.
6. Use glossary terms when provided.
7. Carry-over context is reference only — do not translate those blocks.
"""

NONFICTION_DEFAULT_PROMPT = """You are a professional translator for non-fiction (politics, economics, history, science, technical writing).
Translate content blocks from {{source_language_name}} to {{target_language_name}}.

Rules:
1. Return ONLY JSON: {"translations": [{"id": "<block_id>", "text": "<translated text>"}, ...]}
2. Every source id must appear exactly once. No missing, extra, or duplicate ids.
3. Do not alter block ids.
4. Prioritize accuracy, clarity, and logical structure over literary style.
5. Keep terminology consistent; do not add novelistic embellishment.
6. Use glossary terms when provided.
7. Carry-over context is reference only — do not translate those blocks.
"""


def default_prompt_for_style(style: str) -> str:
    s = (style or "").strip().lower()
    if s in ("nonfiction", "non-fiction", "non_fiction"):
        return NONFICTION_DEFAULT_PROMPT
    return FICTION_DEFAULT_PROMPT


def resolve_system_prompt(style: str, custom: str | None = None) -> str:
    """Custom prompt wins when non-empty; otherwise style default (still a template)."""
    if custom and custom.strip():
        return custom.strip()
    return default_prompt_for_style(style)


def render_prompt_template(
    template: str,
    *,
    source_lang: str | None = None,
    target_lang: str | None = None,
    text: str | None = None,
) -> str:
    """Replace {{...}} variables using language registry names and optional text."""
    src_code = normalize_code(source_lang)
    tgt_code = normalize_code(target_lang)
    src_name = code_to_name(src_code)
    tgt_name = code_to_name(tgt_code)
    out = template
    replacements = {
        "{{source_language}}": src_code,
        "{{source_language_name}}": src_name,
        "{{target_language}}": tgt_code,
        "{{target_language_name}}": tgt_name,
        "{{text}}": text if text is not None else "",
    }
    for key, val in replacements.items():
        out = out.replace(key, val)
    return out


def build_user_payload(
    *,
    source_lang: str,
    target_lang: str,
    style: str,
    glossary_entries: list[dict[str, str]],
    carry_over_source: list[dict[str, str]],
    carry_over_translated: list[dict[str, str]] | None = None,
    to_translate: list[dict[str, str]],
) -> dict:
    """Build AI request payload.

    carry_over_context pairs previous-chunk source with its translation when available
    (spec §20.1). Reference only — never included in required output IDs.
    Language codes are stable; human-readable names belong in the system prompt.
    """
    translated_by_id = {
        item["id"]: item.get("text", "")
        for item in (carry_over_translated or [])
        if item.get("id")
    }
    carry_over_context = []
    for item in carry_over_source or []:
        bid = item.get("id")
        if not bid:
            continue
        entry = {"id": bid, "source": item.get("text", "")}
        if bid in translated_by_id:
            entry["translated"] = translated_by_id[bid]
        carry_over_context.append(entry)

    return {
        "source_language": normalize_code(source_lang),
        "target_language": normalize_code(target_lang),
        "source_language_name": code_to_name(source_lang),
        "target_language_name": code_to_name(target_lang),
        "style": style,
        "glossary": glossary_entries,
        "carry_over_context": carry_over_context,
        "to_translate": to_translate,
    }
