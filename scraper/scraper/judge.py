import json

import anthropic

from .config import MODEL
from .models import JudgeResult, RedditPost

VALID_CATEGORIES = {"clothing", "jewelry", "shoes", "accessory"}

JUDGE_PROMPT = """You are analyzing a Reddit post from r/FashionReps about replica fashion items to decide whether the community is genuinely positive about the item(s) discussed.

Analyze in three tiers, in strict precedence order:
1. COMMUNITY RED FLAGS (highest precedence): explicit callouts by other users — "nice try", "known shill", "buys reviews", direct scam accusations. Any of these go in `red_flags` verbatim (short quotes).
2. SHILL PATTERNS: generic praise with no specifics, throwaway accounts, identical phrasing across comments, no photos where photos are the norm. These lower your sentiment judgment but do NOT go in `red_flags`.
3. GENUINE QUALITY SIGNALS: specific mentions of materials, stitching, weight, engraving, sizing accuracy, comparisons to retail.

Respond with ONLY a JSON object, no other text:
{{
  "positive_sentiment": boolean,   // true only if genuine signals outweigh shill patterns
  "red_flags": [string],           // tier-1 community callouts only; [] if none
  "brand": string or null,         // brand of the main item, e.g. "Chrome Hearts"
  "category": "clothing" | "jewelry" | "shoes" | "accessory" or null,
  "item_name": string or null,     // short item name, e.g. "horseshoe hoodie"
  "quality_summary": string        // one paragraph summarizing genuine quality signals
}}

POST TITLE: {title}

POST BODY:
{body}

TOP COMMENTS:
{comments}
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


def parse_judge_response(text: str) -> JudgeResult:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in judge response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"judge response is not valid JSON: {e}") from e
    if not isinstance(data.get("positive_sentiment"), bool):
        raise ValueError("positive_sentiment missing or not a bool")
    category = data.get("category")
    return JudgeResult(
        positive_sentiment=data["positive_sentiment"],
        red_flags=[str(f) for f in (data.get("red_flags") or [])],
        brand=data.get("brand") or None,
        category=category if category in VALID_CATEGORIES else None,
        item_name=data.get("item_name") or None,
        quality_summary=str(data.get("quality_summary") or ""),
    )


def judge_post(client: anthropic.Anthropic, post: RedditPost) -> JudgeResult:
    prompt = JUDGE_PROMPT.format(
        title=post.title,
        body=post.body[:4000],
        comments="\n---\n".join(post.comments[:40])[:8000],
    )
    last_err: Exception | None = None
    for _ in range(2):  # initial attempt + 1 retry
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return parse_judge_response(_extract_text(message))
        except ValueError as e:
            last_err = e
    raise ValueError(f"judge response unparseable after retry: {last_err}")


def should_ingest(result: JudgeResult) -> bool:
    return result.positive_sentiment and not result.red_flags
