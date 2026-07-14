import json

import anthropic

from .config import MODEL
from .models import Translation, WeidianListing

TRANSLATE_PROMPT = """Translate this Chinese Weidian fashion listing to natural English. Keep brand names and model names as-is. Convert marketing fluff to plain descriptive English.

Respond with ONLY a JSON object, no other text:
{{"title_en": string, "description_en": string}}

TITLE: {title_zh}

DESCRIPTION:
{description_zh}
"""


def _extract_text(message) -> str:
    content = getattr(message, "content", None)
    if not content:
        raise ValueError("empty or non-text response")
    block = content[0]
    text = getattr(block, "text", None)
    if not isinstance(text, str):
        raise ValueError("empty or non-text response")
    return text


def parse_translation(text: str) -> Translation:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in translation response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"translation response is not valid JSON: {e}") from e
    title = data.get("title_en")
    if not title or not isinstance(title, str):
        raise ValueError("title_en missing")
    return Translation(title_en=title, description_en=str(data.get("description_en") or ""))


def translate_listing(client: anthropic.Anthropic, listing: WeidianListing) -> Translation:
    prompt = TRANSLATE_PROMPT.format(
        title_zh=listing.title_zh,
        description_zh=listing.description_zh[:3000],
    )
    last_err: Exception | None = None
    for _ in range(2):
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return parse_translation(_extract_text(message))
        except ValueError as e:
            last_err = e
    raise ValueError(f"translation unparseable after retry: {last_err}")
