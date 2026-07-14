import json
import pathlib

from scraper.reddit import parse_comments, parse_listing

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_listing():
    posts = parse_listing(load("reddit_listing.json"))
    assert len(posts) == 2
    p = posts[0]
    assert p.reddit_post_id == "1abc23"
    assert p.permalink == "https://reddit.com/r/FashionReps/comments/1abc23/chrome_hearts_hoodie_review/"
    assert p.score == 412
    assert p.posted_at == 1752300000
    assert "weidian.com" in p.body
    assert p.comments == []


def test_parse_listing_empty():
    assert parse_listing({"data": {"children": []}}) == []


def test_parse_comments_top_level_only():
    comments = parse_comments(load("reddit_comments.json"))
    assert comments == [
        "W2C: https://weidian.com/item/555",
        "fire hoodie, stitching is clean",
    ]


def test_parse_comments_malformed():
    assert parse_comments([]) == []
    assert parse_comments({"not": "a list"}) == []
