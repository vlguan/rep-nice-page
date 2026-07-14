import json
import types

import pytest

from scraper.judge import judge_post, parse_judge_response, should_ingest
from scraper.models import JudgeResult, RedditPost

GOOD = json.dumps({
    "positive_sentiment": True,
    "red_flags": [],
    "brand": "Chrome Hearts",
    "category": "clothing",
    "item_name": "horseshoe hoodie",
    "quality_summary": "Multiple detailed reviews praise stitching and weight.",
})


def test_parse_good_response():
    r = parse_judge_response(GOOD)
    assert r.positive_sentiment is True
    assert r.brand == "Chrome Hearts"
    assert r.category == "clothing"


def test_parse_strips_markdown_fences():
    r = parse_judge_response(f"```json\n{GOOD}\n```")
    assert r.item_name == "horseshoe hoodie"


def test_parse_invalid_category_becomes_none():
    payload = json.loads(GOOD)
    payload["category"] = "vehicles"
    assert parse_judge_response(json.dumps(payload)).category is None


def test_parse_missing_sentiment_raises():
    with pytest.raises(ValueError):
        parse_judge_response('{"red_flags": []}')


def test_parse_non_json_raises():
    with pytest.raises(ValueError):
        parse_judge_response("sorry, I cannot help with that")


def test_judge_post_raises_value_error_on_empty_content():
    class FakeMessages:
        def create(self, **kwargs):
            return types.SimpleNamespace(content=[])

    class FakeClient:
        messages = FakeMessages()

    post = RedditPost(
        reddit_post_id="abc",
        permalink="/r/FashionReps/comments/abc",
        title="t",
        body="b",
        subreddit="FashionReps",
        score=1,
        num_comments=0,
        posted_at=0,
        comments=[],
    )

    with pytest.raises(ValueError):
        judge_post(FakeClient(), post)


def test_should_ingest():
    ok = JudgeResult(True, [], "b", "clothing", "x", "s")
    flagged = JudgeResult(True, ["known shill, buys reviews"], "b", "clothing", "x", "s")
    negative = JudgeResult(False, [], "b", "clothing", "x", "s")
    assert should_ingest(ok) is True
    assert should_ingest(flagged) is False
    assert should_ingest(negative) is False
