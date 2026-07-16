"""Scrapling-based discovery from old.reddit.com HTML.

Reddit's bot wall 403s unauthenticated JSON endpoints and plain HTTP
clients (httpx, curl, headless Chromium, curl-cffi all blocked);
Camoufox via StealthyFetcher gets through. Used as the default
transport when no Reddit OAuth credentials are configured.
"""

import logging
import re
import time
from urllib.parse import quote, urlparse

from scrapling.parser import Selector

from .config import (
    BACKFILL_LISTINGS,
    DAILY_LISTINGS,
    DISCOVER_LIMIT,
    DISCOVER_LIMIT_BACKFILL,
    REQUEST_DELAY,
    SEARCH_LIMIT,
    SEARCH_QUERIES,
    SUBREDDIT,
)
from .models import RedditPost

logger = logging.getLogger(__name__)

BASE = "https://old.reddit.com"
FETCH_TIMEOUT_MS = 60_000

# old.reddit listing tokens differ from the OAuth API query format.
_LISTING_PATHS = {
    "top?t=week": "top/?t=week",
    "top?t=month": "top/?t=month",
    "hot": "hot/",
}
_COMMENTS_RE = re.compile(r"/comments/([a-z0-9]+)/", re.I)


FETCH_RETRIES = 3


def _fetch(url: str) -> Selector:
    """Fetch a page via camoufox, retrying transient browser-launch hangs.

    A single wedged headless-browser launch would otherwise abort a whole
    backfill, so failed attempts are retried with a fresh browser.
    """
    from scrapling.fetchers import StealthyFetcher

    last_err: Exception | None = None
    for attempt in range(FETCH_RETRIES):
        try:
            page = StealthyFetcher.fetch(
                url, headless=True, network_idle=True, timeout=FETCH_TIMEOUT_MS
            )
            if page.status == 200:
                return page
            last_err = RuntimeError(f"fetch failed ({page.status}): {url}")
        except Exception as e:  # browser launch/timeout/navigation errors
            last_err = e
            logger.warning("fetch attempt %d/%d failed for %s: %s", attempt + 1, FETCH_RETRIES, url, e)
        time.sleep(REQUEST_DELAY * (attempt + 1))
    raise last_err


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


def parse_search_page(page: Selector) -> tuple[list[RedditPost], str | None]:
    """Parse old.reddit search results (markup differs from listing pages).

    Each result exposes the post via its comments link; score/comment counts
    aren't reliably present, so they default to 0 and get filled when the
    post's comments page is fetched downstream.
    """
    posts = []
    for result in page.css("div.search-result-link"):
        hrefs = result.css("a.search-comments::attr(href)")
        if not hrefs:
            hrefs = result.css("a.search-title::attr(href)")
        if not hrefs:
            continue
        href = str(hrefs[0])
        match = _COMMENTS_RE.search(href)
        if not match:
            continue
        titles = result.css("a.search-title::text")
        posts.append(
            RedditPost(
                reddit_post_id=match.group(1),
                permalink=f"https://reddit.com{urlparse(href).path}",
                title=str(titles[0]) if titles else "",
                body="",
                subreddit=SUBREDDIT,
                score=0,
                num_comments=0,
                posted_at=0,
            )
        )
    next_links = page.css("a[rel~='next']::attr(href)")
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


def _walk(start: str, parse, limit: int, posts: list, seen: set) -> None:
    """Follow `next` pagination from `start`, deduping posts into the catalog.

    A page that fails to fetch (after retries) ends this source's walk rather
    than aborting discovery, so one bad page can't sink a whole backfill.
    """
    url: str | None = start
    collected = 0
    while url and collected < limit:
        try:
            page_posts, url = parse(_fetch(url))
        except Exception:
            logger.warning("discovery page failed, stopping this source: %s", url, exc_info=True)
            break
        if not page_posts:
            break
        for post in page_posts:
            collected += 1
            if post.reddit_post_id not in seen:
                seen.add(post.reddit_post_id)
                posts.append(post)
        time.sleep(REQUEST_DELAY)


def discover_posts(backfill: bool = False) -> list[RedditPost]:
    """Discover candidate posts from listings plus spreadsheet search queries.

    `backfill` swaps the lean daily listings for the heavier month sweep; the
    search queries run in both modes so new W2C sheets surface every pass.
    """
    listings = BACKFILL_LISTINGS if backfill else DAILY_LISTINGS
    limit = DISCOVER_LIMIT_BACKFILL if backfill else DISCOVER_LIMIT
    posts: list[RedditPost] = []
    seen: set[str] = set()
    for listing in listings:
        _walk(f"{BASE}/r/{SUBREDDIT}/{_LISTING_PATHS[listing]}", parse_listing_page, limit, posts, seen)
    for query in SEARCH_QUERIES:
        start = f"{BASE}/r/{SUBREDDIT}/search?q={quote(query)}&restrict_sr=on&sort=new&include_over_18=on"
        _walk(start, parse_search_page, SEARCH_LIMIT, posts, seen)
    return posts


def fetch_post_comments(post: RedditPost) -> list[str]:
    path = post.permalink.removeprefix("https://reddit.com")
    texts = parse_post_page(_fetch(f"{BASE}{path}"))
    time.sleep(REQUEST_DELAY)
    return texts
