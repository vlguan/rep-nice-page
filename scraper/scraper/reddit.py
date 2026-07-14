import time

import httpx

from .config import DISCOVER_LIMIT, REQUEST_DELAY, SUBREDDIT, USER_AGENT
from .models import RedditPost

BASE = "https://old.reddit.com"
HEADERS = {"User-Agent": USER_AGENT}


def parse_listing(payload: dict) -> list[RedditPost]:
    posts = []
    for child in payload.get("data", {}).get("children", []):
        d = child.get("data", {})
        if not d.get("id"):
            continue
        posts.append(
            RedditPost(
                reddit_post_id=d["id"],
                permalink=f"https://reddit.com{d.get('permalink', '')}",
                title=d.get("title", ""),
                body=d.get("selftext") or "",
                subreddit=d.get("subreddit", SUBREDDIT),
                score=int(d.get("score") or 0),
                num_comments=int(d.get("num_comments") or 0),
                posted_at=int(d.get("created_utc") or 0),
            )
        )
    return posts


def parse_comments(payload) -> list[str]:
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    out = []
    for child in payload[1].get("data", {}).get("children", []):
        if child.get("kind") == "t1":
            body = child.get("data", {}).get("body", "")
            if body:
                out.append(body)
    return out


def fetch_json(client: httpx.Client, url: str, retries: int = 3):
    for attempt in range(retries):
        resp = client.get(url, headers=HEADERS, follow_redirects=True)
        if resp.status_code == 429:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"rate limited after {retries} attempts: {url}")


def discover_posts(client: httpx.Client, limit: int = DISCOVER_LIMIT) -> list[RedditPost]:
    posts: list[RedditPost] = []
    seen: set[str] = set()
    for path in (
        f"/r/{SUBREDDIT}/top.json?t=week&limit={limit}",
        f"/r/{SUBREDDIT}/hot.json?limit={limit}",
    ):
        for post in parse_listing(fetch_json(client, BASE + path)):
            if post.reddit_post_id not in seen:
                seen.add(post.reddit_post_id)
                posts.append(post)
        time.sleep(REQUEST_DELAY)
    return posts


def fetch_post_comments(client: httpx.Client, post: RedditPost) -> list[str]:
    url = f"{BASE}/r/{post.subreddit}/comments/{post.reddit_post_id}.json?limit=50"
    payload = fetch_json(client, url)
    time.sleep(REQUEST_DELAY)
    return parse_comments(payload)
