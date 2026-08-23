"""Default translation prompts."""

DEFAULT_SYSTEM_PROMPT = """You are a professional book translator.
Translate the given content blocks into the target language.

Rules:
1. Return ONLY a JSON object of the form:
   {"translations": [{"id": "<block_id>", "text": "<translated text>"}, ...]}
2. Every source id must appear exactly once in the output. No missing, no extra, no duplicate ids.
3. Do not translate or alter block ids.
4. If a block is already in the target language, output it unchanged — do not polish or rewrite.
5. Preserve tone and meaning. Apply the requested style.
6. Use the provided glossary terms when applicable (respect inflection / honorifics but keep the specified root translation).
7. Carry-over context is for reference only — do NOT translate those blocks; only translate the "to_translate" list.
"""


def build_user_payload(
    *,
    source_lang: str,
    target_lang: str,
    style: str,
    glossary_entries: list[dict[str, str]],
    carry_over: list[dict[str, str]],
    to_translate: list[dict[str, str]],
) -> dict:
    return {
        "source_language": source_lang,
        "target_language": target_lang,
        "style": style,
        "glossary": glossary_entries,
        "carry_over_context": carry_over,
        "to_translate": to_translate,
    }
