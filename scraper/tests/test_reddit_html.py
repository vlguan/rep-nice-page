import pathlib

from scrapling.parser import Selector

from scraper.reddit_html import discover_posts, parse_listing_page, parse_post_page, parse_search_page

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return Selector(content=(FIXTURES / name).read_text())


def test_parse_listing_page():
    posts, next_url = parse_listing_page(load("reddit_listing.html"))
    assert len(posts) == 2  # promoted post skipped
    p = posts[0]
    assert p.reddit_post_id == "1abc23"
    assert p.permalink == "https://reddit.com/r/FashionReps/comments/1abc23/chrome_hearts_hoodie_review/"
    assert p.title == "Chrome Hearts hoodie review [W2C in comments]"
    assert p.score == 412
    assert p.num_comments == 57
    assert p.posted_at == 1752300000
    assert p.subreddit == "FashionReps"
    assert next_url == "https://old.reddit.com/r/FashionReps/top/?t=week&count=25&after=t3_1def45"


def test_parse_listing_page_empty():
    posts, next_url = parse_listing_page(Selector(content="<html><body></body></html>"))
    assert posts == []
    assert next_url is None


def test_parse_search_page():
    posts, next_url = parse_search_page(load("reddit_search.html"))
    assert len(posts) == 2  # subreddit result (no comments link) skipped
    p = posts[0]
    assert p.reddit_post_id == "abc123"
    assert p.permalink == "https://reddit.com/r/FashionReps/comments/abc123/the_big_w2c_spreadsheet/"
    assert p.title == "The big W2C spreadsheet"
    assert p.subreddit == "FashionReps"
    assert posts[1].reddit_post_id == "def456"
    assert next_url == "https://old.reddit.com/r/FashionReps/search?q=spreadsheet&count=25&after=t3_def456"


def test_parse_search_page_empty():
    posts, next_url = parse_search_page(Selector(content="<html><body></body></html>"))
    assert posts == []
    assert next_url is None


def test_discover_posts_daily_vs_backfill_and_search(monkeypatch):
    """Daily hits week+hot+search; backfill adds top?t=month. All deduped."""
    import scraper.reddit_html as rh

    fetched: list[str] = []

    def fake_fetch(url):
        fetched.append(url)
        return Selector(content="<html><body></body></html>")  # empty -> one hit each

    monkeypatch.setattr(rh, "_fetch", fake_fetch)
    monkeypatch.setattr(rh, "REQUEST_DELAY", 0)

    fetched.clear()
    discover_posts(backfill=False)
    daily = "\n".join(fetched)
    assert "/top/?t=week" in daily
    assert "/hot/" in daily
    assert "/top/?t=month" not in daily
    assert daily.count("/search?q=") == 4  # one per SEARCH_QUERIES entry

    fetched.clear()
    discover_posts(backfill=True)
    assert any("/top/?t=month" in u for u in fetched)


def test_parse_post_page_selftext_comments_and_hrefs():
    texts = parse_post_page(load("reddit_post.html"))
    # selftext first, then top-level comments only
    assert len(texts) == 3
    assert "Quality is insane" in texts[0]
    assert "https://weidian.com/item.html?itemID=7123456789" in texts[0]  # href harvested
    assert "https://weidian.com/item/555" in texts[1]
    assert "fire hoodie" in texts[2]
    assert not any("nested reply" in t for t in texts)
