import os
import time

import httpx

from .config import DISCOVER_LIMIT, REQUEST_DELAY, SUBREDDIT, USER_AGENT
from .models import RedditPost

# Reddit blocks unauthenticated .json endpoints (Fastly bot wall), so all
# listing/comment reads go through the official OAuth API.
API_BASE = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


def oauth_client(
    client_id: str | None = None, client_secret: str | None = None
) -> httpx.Client:
    """Application-only (client_credentials) OAuth client for read-only access."""
    client_id = client_id or os.environ["REDDIT_CLIENT_ID"]
    client_secret = client_secret or os.environ["REDDIT_CLIENT_SECRET"]
    resp = httpx.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"}
    )


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
        resp = client.get(url, follow_redirects=True)
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
        f"/r/{SUBREDDIT}/top?t=week&limit={limit}",
        f"/r/{SUBREDDIT}/hot?limit={limit}",
    ):
        for post in parse_listing(fetch_json(client, API_BASE + path)):
            if post.reddit_post_id not in seen:
                seen.add(post.reddit_post_id)
                posts.append(post)
        time.sleep(REQUEST_DELAY)
    return posts


def fetch_post_comments(client: httpx.Client, post: RedditPost) -> list[str]:
    url = f"{API_BASE}/r/{post.subreddit}/comments/{post.reddit_post_id}?limit=50&depth=1"
    payload = fetch_json(client, url)
    time.sleep(REQUEST_DELAY)
    return parse_comments(payload)
