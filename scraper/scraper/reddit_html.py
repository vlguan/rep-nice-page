"""Scrapling-based discovery from old.reddit.com HTML.

Reddit's bot wall 403s unauthenticated JSON endpoints and plain HTTP
clients (httpx, curl, headless Chromium, curl-cffi all blocked);
Camoufox via StealthyFetcher gets through. Used as the default
transport when no Reddit OAuth credentials are configured.
"""

import time

from scrapling.parser import Selector

from .config import DISCOVER_LIMIT, REQUEST_DELAY, SUBREDDIT
from .models import RedditPost

BASE = "https://old.reddit.com"
FETCH_TIMEOUT_MS = 60_000


def _fetch(url: str) -> Selector:
    from scrapling.fetchers import StealthyFetcher

    page = StealthyFetcher.fetch(
        url, headless=True, network_idle=True, timeout=FETCH_TIMEOUT_MS
    )
    if page.status != 200:
        raise RuntimeError(f"fetch failed ({page.status}): {url}")
    return page


def _text_with_links(node) -> str:
    # Weidian links usually live in <a href>, not the visible text.
    text = node.get_all_text(strip=True)
    hrefs = [str(h) for h in node.css("a::attr(href)")]
    return "\n".join([text, *hrefs]).strip()


def parse_listing_page(page: Selector) -> tuple[list[RedditPost], str | None]:
    posts = []
    for thing in page.css("div.thing"):
        attrs = thing.attrib
        fullname = attrs.get("data-fullname", "")
        if not fullname.startswith("t3_") or attrs.get("data-promoted") == "true":
            continue
        titles = thing.css("a.title::text")
        posts.append(
            RedditPost(
                reddit_post_id=fullname.removeprefix("t3_"),
                permalink=f"https://reddit.com{attrs.get('data-permalink', '')}",
                title=str(titles[0]) if titles else "",
                body="",  # selftext arrives with the comments-page fetch
                subreddit=attrs.get("data-subreddit", SUBREDDIT),
                score=int(attrs.get("data-score") or 0),
                num_comments=int(attrs.get("data-comments-count") or 0),
                posted_at=int(int(attrs.get("data-timestamp") or 0) / 1000),
            )
        )
    next_links = page.css("span.next-button a::attr(href)")
    return posts, (str(next_links[0]) if next_links else None)


def parse_post_page(page: Selector) -> list[str]:
    """Selftext (if any) followed by top-level comment texts, hrefs included."""
    texts = []
    self_bodies = page.css("div.thing.self div.usertext-body")
    if self_bodies:
        texts.append(_text_with_links(self_bodies[0]))
    for comment in page.css("div.commentarea > div.sitetable > div.thing.comment"):
        # Live pages wrap the body in <form class="usertext">, so a child
        # combinator never matches; descendants include nested replies' bodies,
        # but the comment's own body always comes first in document order.
        bodies = comment.css("div.entry div.usertext-body")
        if bodies:
            texts.append(_text_with_links(bodies[0]))
    return [t for t in texts if t]


def discover_posts(limit: int = DISCOVER_LIMIT) -> list[RedditPost]:
    posts: list[RedditPost] = []
    seen: set[str] = set()
    for start in (
        f"{BASE}/r/{SUBREDDIT}/top/?t=week",
        f"{BASE}/r/{SUBREDDIT}/top/?t=month",
        f"{BASE}/r/{SUBREDDIT}/hot/",
    ):
        url: str | None = start
        collected = 0
        while url and collected < limit:
            page_posts, url = parse_listing_page(_fetch(url))
            if not page_posts:
                break
            for post in page_posts:
                collected += 1
                if post.reddit_post_id not in seen:
                    seen.add(post.reddit_post_id)
                    posts.append(post)
            time.sleep(REQUEST_DELAY)
    return posts


def fetch_post_comments(post: RedditPost) -> list[str]:
    path = post.permalink.removeprefix("https://reddit.com")
    texts = parse_post_page(_fetch(f"{BASE}{path}"))
    time.sleep(REQUEST_DELAY)
    return texts
