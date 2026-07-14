# rep-nice-page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public website that auto-surfaces replica fashion items trending on r/FashionReps, enriched from Weidian (translated, photos), stored in Postgres, with Superbuy handoff and daily dead-link revalidation.

**Architecture:** Monorepo with two Railway services sharing Railway Postgres: `scraper/` (Python daily cron: discover → judge → enrich → revalidate) and `web/` (Next.js App Router, read-only catalog). Postgres is the only interface between them.

**Tech Stack:** Python 3.12, httpx, playwright, anthropic, psycopg 3, pytest · Next.js 15 (App Router), Drizzle ORM, postgres.js, Tailwind, vitest.

**Spec:** `docs/superpowers/specs/2026-07-13-rep-nice-page-design.md`

## Global Constraints

- LLM model everywhere: `claude-haiku-4-5-20251001`. Max 1 retry on unparseable LLM response, then skip the item/post.
- Canonical Weidian URL form: `https://weidian.com/item.html?itemID=<digits>` — everything is normalized to this before dedupe or storage.
- Superbuy handoff: `https://www.superbuy.com/en/page/buy/?url=<URL-encoded weidian_url>` — no API.
- `items.status` is only ever `'active'` or `'inactive'`. Revalidation may deactivate ONLY on confirmed death (removal-notice text or HTTP 404). Timeout/network error = no status change.
- Images are hotlinked Weidian URLs; UI must render a local placeholder on load error. Use plain `<img referrerPolicy="no-referrer">`, never `next/image` (hotlink referer checks).
- All public web queries filter `status = 'active'`.
- Reddit access via public JSON endpoints on `old.reddit.com` with User-Agent `rep-nice-page/1.0 (personal aggregator)`, 1.5s delay between requests, exponential backoff on 429.
- Scraper DB tests and web query tests require `TEST_DATABASE_URL`; they must auto-skip when unset.
- Python code lives under `scraper/scraper/`; run tests with `cd scraper && python -m pytest`. Web tests: `cd web && npx vitest run`.
- Commit after every green test cycle. Commit messages: conventional (`feat:`, `test:`, `chore:`).

---

### Task 1: Monorepo scaffold + scraper package skeleton

**Files:**
- Create: `.gitignore`, `README.md`
- Create: `scraper/requirements.txt`, `scraper/pytest.ini`
- Create: `scraper/scraper/__init__.py`, `scraper/scraper/config.py`, `scraper/scraper/models.py`
- Test: `scraper/tests/__init__.py`, `scraper/tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: dataclasses `RedditPost`, `JudgeResult`, `WeidianListing`, `Translation` in `scraper.models`; constants in `scraper.config` (`MODEL`, `USER_AGENT`, `REQUEST_DELAY`, `SUBREDDIT`, `CNY_TO_USD` not here — web-only). Every later scraper task imports these.

- [ ] **Step 1: Create scaffold files**

`.gitignore`:
```
node_modules/
.next/
__pycache__/
*.pyc
.env
.env.*
.venv/
.pytest_cache/
```

`README.md`:
```markdown
# rep-nice-page

Public catalog of replica fashion items trending on r/FashionReps, enriched from Weidian, with Superbuy handoff.

- `web/` — Next.js catalog site (Railway service)
- `scraper/` — Python daily pipeline (Railway cron service)
- Spec: `docs/superpowers/specs/2026-07-13-rep-nice-page-design.md`
```

`scraper/requirements.txt`:
```
httpx==0.27.*
anthropic>=0.40
psycopg[binary]==3.2.*
playwright==1.49.*
pytest==8.*
```

`scraper/pytest.ini`:
```ini
[pytest]
testpaths = tests
```

`scraper/scraper/config.py`:
```python
MODEL = "claude-haiku-4-5-20251001"
USER_AGENT = "rep-nice-page/1.0 (personal aggregator)"
REQUEST_DELAY = 1.5  # seconds between Reddit requests
SUBREDDIT = "FashionReps"
DISCOVER_LIMIT = 100  # posts per listing endpoint
```

`scraper/scraper/models.py`:
```python
from dataclasses import dataclass, field


@dataclass
class RedditPost:
    reddit_post_id: str
    permalink: str
    title: str
    body: str
    subreddit: str
    score: int
    num_comments: int
    posted_at: int  # unix epoch UTC
    comments: list[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    positive_sentiment: bool
    red_flags: list[str]        # tier-1 community callouts ONLY
    brand: str | None
    category: str | None        # clothing | jewelry | shoes | accessory
    item_name: str | None
    quality_summary: str


@dataclass
class WeidianListing:
    weidian_url: str            # canonical form
    weidian_item_id: str | None
    title_zh: str
    description_zh: str
    price_cny: float | None
    seller_name: str | None
    image_urls: list[str]


@dataclass
class Translation:
    title_en: str
    description_en: str
```

Create empty `scraper/scraper/__init__.py` and `scraper/tests/__init__.py`.

- [ ] **Step 2: Write smoke test**

`scraper/tests/test_models.py`:
```python
from scraper.models import RedditPost


def test_redditpost_defaults():
    p = RedditPost(
        reddit_post_id="abc", permalink="https://reddit.com/x", title="t",
        body="", subreddit="FashionReps", score=1, num_comments=0, posted_at=0,
    )
    assert p.comments == []
```

- [ ] **Step 3: Create venv, install, run test**

Run: `cd scraper && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest -v`
Expected: 1 passed

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md scraper
git commit -m "chore: monorepo scaffold + scraper package skeleton"
```

---

### Task 2: Web scaffold + Drizzle schema + migration SQL

**Files:**
- Create: `web/` via create-next-app
- Create: `web/src/db/schema.ts`, `web/src/db/client.ts`, `web/drizzle.config.ts`
- Create (generated): `web/drizzle/0000_init.sql`

**Interfaces:**
- Consumes: nothing
- Produces: Postgres schema (tables `items`, `reddit_posts`, `item_mentions`, `scrape_runs` exactly as below). The migration SQL at `web/drizzle/*.sql` is applied by scraper test conftest (Task 8) and by deploy docs (Task 13). Drizzle tables exported as `items`, `redditPosts`, `itemMentions`, `scrapeRuns`; `db` client exported from `web/src/db/client.ts`.

- [ ] **Step 1: Scaffold Next.js app**

Run: `npx create-next-app@latest web --ts --tailwind --eslint --app --src-dir --use-npm --no-import-alias --turbopack`
Then: `cd web && npm install drizzle-orm postgres && npm install -D drizzle-kit vitest dotenv`

- [ ] **Step 2: Write schema**

`web/src/db/schema.ts`:
```typescript
import {
  pgTable, serial, text, integer, numeric, jsonb, timestamp, primaryKey,
} from "drizzle-orm/pg-core";

export const items = pgTable("items", {
  id: serial("id").primaryKey(),
  weidianUrl: text("weidian_url").notNull().unique(),
  weidianItemId: text("weidian_item_id"),
  titleZh: text("title_zh"),
  titleEn: text("title_en"),
  descriptionEn: text("description_en"),
  brand: text("brand"),
  category: text("category"), // clothing | jewelry | shoes | accessory
  priceCny: numeric("price_cny"),
  sellerName: text("seller_name"),
  imageUrls: jsonb("image_urls").$type<string[]>(),
  status: text("status").notNull().default("active"), // active | inactive
  lastValidatedAt: timestamp("last_validated_at", { withTimezone: true }),
  deadSince: timestamp("dead_since", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const redditPosts = pgTable("reddit_posts", {
  id: serial("id").primaryKey(),
  redditPostId: text("reddit_post_id").notNull().unique(),
  permalink: text("permalink"),
  title: text("title"),
  subreddit: text("subreddit"),
  score: integer("score"),
  numComments: integer("num_comments"),
  postedAt: timestamp("posted_at", { withTimezone: true }),
  scrapedAt: timestamp("scraped_at", { withTimezone: true }),
  sentiment: text("sentiment"), // positive | negative | flagged | null (no weidian link)
  aiSummary: text("ai_summary"),
});

export const itemMentions = pgTable(
  "item_mentions",
  {
    itemId: integer("item_id").notNull().references(() => items.id),
    redditPostId: integer("reddit_post_id").notNull().references(() => redditPosts.id),
  },
  (t) => [primaryKey({ columns: [t.itemId, t.redditPostId] })],
);

export const scrapeRuns = pgTable("scrape_runs", {
  id: serial("id").primaryKey(),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  postsSeen: integer("posts_seen"),
  itemsAdded: integer("items_added"),
  itemsDeactivated: integer("items_deactivated"),
  error: text("error"),
});
```

`web/drizzle.config.ts`:
```typescript
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL ?? "" },
});
```

`web/src/db/client.ts`:
```typescript
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL!;
const client = postgres(connectionString, { prepare: false });
export const db = drizzle(client, { schema });
```

- [ ] **Step 3: Generate migration and verify**

Run: `cd web && npx drizzle-kit generate --name init`
Expected: `web/drizzle/0000_init.sql` created containing `CREATE TABLE "items"`, `"reddit_posts"`, `"item_mentions"`, `"scrape_runs"`.
Run: `npx tsc --noEmit` — Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web
git commit -m "feat: web scaffold with drizzle schema and initial migration"
```

---

### Task 3: Weidian URL extraction + normalization

**Files:**
- Create: `scraper/scraper/extract.py`
- Test: `scraper/tests/test_extract.py`

**Interfaces:**
- Consumes: nothing
- Produces: `extract_weidian_urls(text: str) -> list[str]` (canonical URLs, deduped, order-preserving); `extract_item_ids(text: str) -> list[str]`; `canonical_url(item_id: str) -> str`. Used by Task 10 orchestrator.

- [ ] **Step 1: Write failing tests**

`scraper/tests/test_extract.py`:
```python
from scraper.extract import canonical_url, extract_item_ids, extract_weidian_urls


def test_canonical_url():
    assert canonical_url("7123456789") == "https://weidian.com/item.html?itemID=7123456789"


def test_extracts_item_html_form_with_tracking_params():
    text = "check https://weidian.com/item.html?itemID=7123456789&spider_token=4a9c&wfr=c ok"
    assert extract_weidian_urls(text) == ["https://weidian.com/item.html?itemID=7123456789"]


def test_extracts_path_forms():
    text = "a https://weidian.com/item/111 b http://www.weidian.com/items/222?x=1 c"
    assert extract_item_ids(text) == ["111", "222"]


def test_dedupes_same_item_across_forms():
    text = "https://weidian.com/item/333 and https://weidian.com/item.html?itemID=333"
    assert extract_weidian_urls(text) == ["https://weidian.com/item.html?itemID=333"]


def test_no_urls():
    assert extract_weidian_urls("nothing here, taobao.com/item/999 is not weidian") == []


def test_handles_none_and_markdown_wrapping():
    assert extract_weidian_urls("") == []
    text = "[link](https://weidian.com/item.html?itemID=444)"
    assert extract_item_ids(text) == ["444"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.extract'`

- [ ] **Step 3: Implement**

`scraper/scraper/extract.py`:
```python
import re

_PATTERNS = [
    re.compile(r"weidian\.com/item\.html\?[^\s\"'<>()\[\]]*?itemID=(\d+)", re.I),
    re.compile(r"weidian\.com/items?/(\d+)", re.I),
]


def canonical_url(item_id: str) -> str:
    return f"https://weidian.com/item.html?itemID={item_id}"


def extract_item_ids(text: str) -> list[str]:
    ids: list[str] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            item_id = match.group(1)
            if item_id not in ids:
                ids.append(item_id)
    return ids


def extract_weidian_urls(text: str) -> list[str]:
    return [canonical_url(i) for i in extract_item_ids(text)]
```

- [ ] **Step 4: Run tests, expect pass**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_extract.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/extract.py scraper/tests/test_extract.py
git commit -m "feat: weidian url extraction and canonicalization"
```

---

### Task 4: Reddit discovery client

**Files:**
- Create: `scraper/scraper/reddit.py`
- Create: `scraper/tests/fixtures/reddit_listing.json`, `scraper/tests/fixtures/reddit_comments.json`
- Test: `scraper/tests/test_reddit.py`

**Interfaces:**
- Consumes: `RedditPost` from `scraper.models`; `USER_AGENT`, `REQUEST_DELAY`, `SUBREDDIT`, `DISCOVER_LIMIT` from `scraper.config`
- Produces: `parse_listing(payload: dict) -> list[RedditPost]`; `parse_comments(payload: list) -> list[str]`; `fetch_json(client: httpx.Client, url: str) -> dict | list`; `discover_posts(client: httpx.Client, limit: int = DISCOVER_LIMIT) -> list[RedditPost]` (top?t=week + hot, deduped); `fetch_post_comments(client: httpx.Client, post: RedditPost) -> list[str]`. Used by Task 10.

- [ ] **Step 1: Create fixtures**

`scraper/tests/fixtures/reddit_listing.json` (shape of `/top.json`):
```json
{
  "kind": "Listing",
  "data": {
    "children": [
      {
        "kind": "t3",
        "data": {
          "id": "1abc23",
          "permalink": "/r/FashionReps/comments/1abc23/chrome_hearts_hoodie_review/",
          "title": "Chrome Hearts hoodie review [W2C in comments]",
          "selftext": "Quality is insane. https://weidian.com/item.html?itemID=7123456789",
          "subreddit": "FashionReps",
          "score": 412,
          "num_comments": 57,
          "created_utc": 1752300000.0
        }
      },
      {
        "kind": "t3",
        "data": {
          "id": "1def45",
          "permalink": "/r/FashionReps/comments/1def45/haul_pics/",
          "title": "Haul pics",
          "selftext": "",
          "subreddit": "FashionReps",
          "score": 88,
          "num_comments": 12,
          "created_utc": 1752200000.0
        }
      }
    ]
  }
}
```

`scraper/tests/fixtures/reddit_comments.json` (shape of `/comments/<id>.json` — array of two listings; second is comments):
```json
[
  { "kind": "Listing", "data": { "children": [] } },
  {
    "kind": "Listing",
    "data": {
      "children": [
        { "kind": "t1", "data": { "body": "W2C: https://weidian.com/item/555" } },
        { "kind": "t1", "data": { "body": "fire hoodie, stitching is clean" } },
        { "kind": "more", "data": {} }
      ]
    }
  }
]
```

- [ ] **Step 2: Write failing tests**

`scraper/tests/test_reddit.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_reddit.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`scraper/scraper/reddit.py`:
```python
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
```

- [ ] **Step 5: Run tests, expect pass**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_reddit.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scraper/scraper/reddit.py scraper/tests/test_reddit.py scraper/tests/fixtures
git commit -m "feat: reddit json discovery client"
```

---

### Task 5: LLM judge

**Files:**
- Create: `scraper/scraper/judge.py`
- Test: `scraper/tests/test_judge.py`

**Interfaces:**
- Consumes: `JudgeResult`, `RedditPost` from `scraper.models`; `MODEL` from `scraper.config`
- Produces: `parse_judge_response(text: str) -> JudgeResult` (raises `ValueError` on bad payload); `judge_post(client: anthropic.Anthropic, post: RedditPost) -> JudgeResult` (1 retry then raises `ValueError`); `should_ingest(result: JudgeResult) -> bool` (positive AND no tier-1 red flags). Used by Task 10.

- [ ] **Step 1: Write failing tests**

`scraper/tests/test_judge.py`:
```python
import json

import pytest

from scraper.judge import parse_judge_response, should_ingest
from scraper.models import JudgeResult

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


def test_should_ingest():
    ok = JudgeResult(True, [], "b", "clothing", "x", "s")
    flagged = JudgeResult(True, ["known shill, buys reviews"], "b", "clothing", "x", "s")
    negative = JudgeResult(False, [], "b", "clothing", "x", "s")
    assert should_ingest(ok) is True
    assert should_ingest(flagged) is False
    assert should_ingest(negative) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`scraper/scraper/judge.py`:
```python
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
            return parse_judge_response(message.content[0].text)
        except ValueError as e:
            last_err = e
    raise ValueError(f"judge response unparseable after retry: {last_err}")


def should_ingest(result: JudgeResult) -> bool:
    return result.positive_sentiment and not result.red_flags
```

- [ ] **Step 4: Run tests, expect pass**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_judge.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/judge.py scraper/tests/test_judge.py
git commit -m "feat: llm judge with shill-tier logic"
```

---

### Task 6: Weidian page parsing + liveness detection

**Files:**
- Create: `scraper/scraper/weidian.py`
- Create: `scraper/tests/fixtures/weidian_live.html`, `scraper/tests/fixtures/weidian_dead.html`
- Test: `scraper/tests/test_weidian.py`

**Interfaces:**
- Consumes: `WeidianListing` from `scraper.models`; `USER_AGENT` from `scraper.config`
- Produces: `Liveness` enum (`LIVE`, `DEAD`, `UNKNOWN`); `detect_liveness(html: str, status_code: int) -> Liveness`; `parse_listing_html(html: str, url: str) -> WeidianListing` (raises `ValueError` if no title found); `fetch_rendered(url: str) -> tuple[str, int]` (Playwright); `fetch_lightweight(url: str) -> tuple[str, int]` (httpx). Used by Tasks 9 and 10.

- [ ] **Step 1: Create fixtures**

`scraper/tests/fixtures/weidian_live.html`:
```html
<!DOCTYPE html><html><head>
<title>CH双面帽衫 高克重 - 微店</title>
<meta property="og:title" content="CH双面帽衫 高克重" />
<meta property="og:description" content="425克重磅面料，刺绣工艺" />
<meta property="og:image" content="https://si.geilicdn.com/item123-main.jpg" />
<meta name="shop_name" content="阿龙定制" />
</head><body>
<script>window.__DATA__ = {"itemID":"7123456789","price":"268.00","shopName":"阿龙定制","imgs":["https://si.geilicdn.com/item123-main.jpg","https://si.geilicdn.com/item123-b.jpg"]}</script>
</body></html>
```

`scraper/tests/fixtures/weidian_dead.html`:
```html
<!DOCTYPE html><html><head><title>微店</title></head>
<body><div class="empty-tip">商品已下架</div></body></html>
```

- [ ] **Step 2: Write failing tests**

`scraper/tests/test_weidian.py`:
```python
import pathlib

import pytest

from scraper.weidian import Liveness, detect_liveness, parse_listing_html

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
LIVE_HTML = (FIXTURES / "weidian_live.html").read_text()
DEAD_HTML = (FIXTURES / "weidian_dead.html").read_text()
URL = "https://weidian.com/item.html?itemID=7123456789"


def test_live_page_detected():
    assert detect_liveness(LIVE_HTML, 200) is Liveness.LIVE


def test_removal_notice_is_dead():
    assert detect_liveness(DEAD_HTML, 200) is Liveness.DEAD


def test_404_is_dead():
    assert detect_liveness("", 404) is Liveness.DEAD


def test_server_error_is_unknown():
    assert detect_liveness("", 503) is Liveness.UNKNOWN


def test_empty_shell_is_unknown():
    assert detect_liveness("<html><body></body></html>", 200) is Liveness.UNKNOWN


def test_parse_listing():
    listing = parse_listing_html(LIVE_HTML, URL)
    assert listing.title_zh == "CH双面帽衫 高克重"
    assert listing.weidian_item_id == "7123456789"
    assert listing.price_cny == 268.0
    assert "https://si.geilicdn.com/item123-main.jpg" in listing.image_urls
    assert listing.description_zh == "425克重磅面料，刺绣工艺"


def test_parse_dead_page_raises():
    with pytest.raises(ValueError):
        parse_listing_html(DEAD_HTML, URL)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_weidian.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`scraper/scraper/weidian.py`:
```python
import re
from enum import Enum

import httpx

from .config import USER_AGENT
from .extract import extract_item_ids
from .models import WeidianListing

DEAD_MARKERS = [
    "商品已下架",
    "该店铺已关闭",
    "商品不存在",
    "店铺不存在",
    "宝贝不存在",
]

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class Liveness(Enum):
    LIVE = "live"
    DEAD = "dead"
    UNKNOWN = "unknown"


def _meta(html: str, prop: str) -> str | None:
    match = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
        html,
        re.I,
    )
    return match.group(1) or None if match else None


def detect_liveness(html: str, status_code: int) -> Liveness:
    if status_code == 404:
        return Liveness.DEAD
    if status_code >= 400:
        return Liveness.UNKNOWN
    if any(marker in html for marker in DEAD_MARKERS):
        return Liveness.DEAD
    if _meta(html, "og:title"):
        return Liveness.LIVE
    return Liveness.UNKNOWN


def parse_listing_html(html: str, url: str) -> WeidianListing:
    title = _meta(html, "og:title")
    if not title:
        raise ValueError(f"no listing title found at {url}")

    price = None
    price_match = re.search(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)', html)
    if price_match:
        price = float(price_match.group(1))

    images: list[str] = []
    og_image = _meta(html, "og:image")
    if og_image:
        images.append(og_image)
    for match in re.finditer(r'https://si\.geilicdn\.com/[^\s"\'\\]+?\.(?:jpg|jpeg|png|webp)', html):
        if match.group(0) not in images:
            images.append(match.group(0))

    seller = _meta(html, "shop_name")
    if not seller:
        seller_match = re.search(r'"shopName"\s*:\s*"([^"]+)"', html)
        seller = seller_match.group(1) if seller_match else None

    ids = extract_item_ids(url)
    id_match = re.search(r'"itemID"\s*:\s*"?(\d+)', html)

    return WeidianListing(
        weidian_url=url,
        weidian_item_id=ids[0] if ids else (id_match.group(1) if id_match else None),
        title_zh=title,
        description_zh=_meta(html, "og:description") or "",
        price_cny=price,
        seller_name=seller,
        image_urls=images,
    )


def fetch_lightweight(url: str, timeout: float = 15.0) -> tuple[str, int]:
    resp = httpx.get(
        url,
        headers={"User-Agent": MOBILE_UA},
        follow_redirects=True,
        timeout=timeout,
    )
    return resp.text, resp.status_code


def fetch_rendered(url: str, timeout_ms: int = 30000) -> tuple[str, int]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=MOBILE_UA)
            resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # let client-side rendering settle
            return page.content(), resp.status if resp else 0
        finally:
            browser.close()
```

- [ ] **Step 5: Run tests, expect pass**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_weidian.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add scraper/scraper/weidian.py scraper/tests/test_weidian.py scraper/tests/fixtures
git commit -m "feat: weidian parsing, liveness detection, fetchers"
```

---

### Task 7: Translation

**Files:**
- Create: `scraper/scraper/translate.py`
- Test: `scraper/tests/test_translate.py`

**Interfaces:**
- Consumes: `WeidianListing`, `Translation` from `scraper.models`; `MODEL` from `scraper.config`
- Produces: `parse_translation(text: str) -> Translation` (raises `ValueError`); `translate_listing(client: anthropic.Anthropic, listing: WeidianListing) -> Translation` (1 retry then raises). Used by Task 10.

- [ ] **Step 1: Write failing tests**

`scraper/tests/test_translate.py`:
```python
import pytest

from scraper.translate import parse_translation


def test_parse_good():
    t = parse_translation('{"title_en": "CH double-sided hoodie", "description_en": "425gsm heavy fabric, embroidered"}')
    assert t.title_en == "CH double-sided hoodie"
    assert "425gsm" in t.description_en


def test_parse_with_fences():
    t = parse_translation('```json\n{"title_en": "a", "description_en": "b"}\n```')
    assert t.title_en == "a"


def test_parse_missing_title_raises():
    with pytest.raises(ValueError):
        parse_translation('{"description_en": "b"}')


def test_parse_non_json_raises():
    with pytest.raises(ValueError):
        parse_translation("no json here")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_translate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`scraper/scraper/translate.py`:
```python
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
            return parse_translation(message.content[0].text)
        except ValueError as e:
            last_err = e
    raise ValueError(f"translation unparseable after retry: {last_err}")
```

- [ ] **Step 4: Run tests, expect pass**

Run: `cd scraper && .venv/bin/python -m pytest tests/test_translate.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/translate.py scraper/tests/test_translate.py
git commit -m "feat: listing translation via claude"
```

---

### Task 8: Scraper DB layer

**Files:**
- Create: `scraper/scraper/db.py`
- Create: `scraper/tests/conftest.py`
- Test: `scraper/tests/test_db.py`

**Interfaces:**
- Consumes: models from `scraper.models`; migration SQL from `web/drizzle/*.sql` (Task 2)
- Produces (all take a `psycopg.Connection` as first arg):
  - `get_conn(database_url: str) -> psycopg.Connection` (autocommit=True)
  - `seen_post_ids(conn, ids: list[str]) -> set[str]`
  - `insert_post(conn, post: RedditPost, sentiment: str | None, ai_summary: str | None) -> int` (upsert on reddit_post_id, returns row id)
  - `upsert_item(conn, listing: WeidianListing, translation: Translation, judge: JudgeResult) -> int` (on conflict weidian_url: reactivate + update, returns id)
  - `link_mention(conn, item_id: int, post_row_id: int) -> None`
  - `get_items_for_validation(conn) -> list[tuple[int, str, str]]` (id, weidian_url, status — ALL items)
  - `set_item_status(conn, item_id: int, status: str) -> None` (manages dead_since + last_validated_at)
  - `touch_validated(conn, item_id: int) -> None`
  - `record_run(conn, started_at, posts_seen: int, items_added: int, items_deactivated: int, error: str | None) -> None`

  Used by Tasks 9 and 10.

- [ ] **Step 1: Write conftest with schema fixture**

`scraper/tests/conftest.py`:
```python
import os
import pathlib

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    import psycopg

    connection = psycopg.connect(TEST_DB, autocommit=True)
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    root = pathlib.Path(__file__).resolve().parents[2]
    for sql_file in sorted((root / "web" / "drizzle").glob("*.sql")):
        for stmt in sql_file.read_text().split("--> statement-breakpoint"):
            if stmt.strip():
                connection.execute(stmt)
    yield connection
    connection.close()
```

- [ ] **Step 2: Write failing tests**

`scraper/tests/test_db.py`:
```python
from datetime import datetime, timezone

from scraper.models import JudgeResult, RedditPost, Translation, WeidianListing
from tests.conftest import requires_db

pytestmark = requires_db

POST = RedditPost(
    reddit_post_id="1abc23", permalink="https://reddit.com/x", title="t",
    body="b", subreddit="FashionReps", score=412, num_comments=57, posted_at=1752300000,
)
LISTING = WeidianListing(
    weidian_url="https://weidian.com/item.html?itemID=7123456789",
    weidian_item_id="7123456789", title_zh="帽衫", description_zh="重磅",
    price_cny=268.0, seller_name="阿龙定制",
    image_urls=["https://si.geilicdn.com/a.jpg"],
)
TRANSLATION = Translation(title_en="CH hoodie", description_en="heavy fabric")
JUDGE = JudgeResult(True, [], "Chrome Hearts", "clothing", "hoodie", "solid reviews")


def test_insert_post_and_seen(conn):
    from scraper import db

    row_id = db.insert_post(conn, POST, "positive", "solid reviews")
    assert isinstance(row_id, int)
    assert db.seen_post_ids(conn, ["1abc23", "zzz"]) == {"1abc23"}
    assert db.insert_post(conn, POST, "positive", "solid reviews") == row_id  # upsert


def test_upsert_item_and_mention(conn):
    from scraper import db

    post_id = db.insert_post(conn, POST, "positive", None)
    item_id = db.upsert_item(conn, LISTING, TRANSLATION, JUDGE)
    db.link_mention(conn, item_id, post_id)
    db.link_mention(conn, item_id, post_id)  # idempotent

    assert db.upsert_item(conn, LISTING, TRANSLATION, JUDGE) == item_id

    rows = db.get_items_for_validation(conn)
    assert rows == [(item_id, LISTING.weidian_url, "active")]


def test_status_transitions(conn):
    from scraper import db

    item_id = db.upsert_item(conn, LISTING, TRANSLATION, JUDGE)
    db.set_item_status(conn, item_id, "inactive")
    row = conn.execute("SELECT status, dead_since FROM items WHERE id=%s", (item_id,)).fetchone()
    assert row[0] == "inactive" and row[1] is not None

    db.set_item_status(conn, item_id, "active")
    row = conn.execute("SELECT status, dead_since FROM items WHERE id=%s", (item_id,)).fetchone()
    assert row[0] == "active" and row[1] is None

    # re-ingesting an inactive item reactivates it
    db.set_item_status(conn, item_id, "inactive")
    db.upsert_item(conn, LISTING, TRANSLATION, JUDGE)
    row = conn.execute("SELECT status FROM items WHERE id=%s", (item_id,)).fetchone()
    assert row[0] == "active"


def test_record_run(conn):
    from scraper import db

    db.record_run(conn, datetime.now(timezone.utc), 200, 5, 2, None)
    row = conn.execute("SELECT posts_seen, items_added, items_deactivated, error FROM scrape_runs").fetchone()
    assert row == (200, 5, 2, None)
```

- [ ] **Step 3: Run to verify failure (needs a local test DB)**

Start a throwaway Postgres if none is running:
`docker run -d --name repnice-test-pg -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:16`
Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.db'`
(Without TEST_DATABASE_URL the tests must SKIP — verify that too: `.venv/bin/python -m pytest tests/test_db.py -v` → 4 skipped.)

- [ ] **Step 4: Implement**

`scraper/scraper/db.py`:
```python
import json
from datetime import datetime

import psycopg

from .models import JudgeResult, RedditPost, Translation, WeidianListing


def get_conn(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=True)


def seen_post_ids(conn: psycopg.Connection, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = conn.execute(
        "SELECT reddit_post_id FROM reddit_posts WHERE reddit_post_id = ANY(%s)",
        (ids,),
    ).fetchall()
    return {r[0] for r in rows}


def insert_post(
    conn: psycopg.Connection, post: RedditPost, sentiment: str | None, ai_summary: str | None
) -> int:
    row = conn.execute(
        """
        INSERT INTO reddit_posts
          (reddit_post_id, permalink, title, subreddit, score, num_comments,
           posted_at, scraped_at, sentiment, ai_summary)
        VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), now(), %s, %s)
        ON CONFLICT (reddit_post_id) DO UPDATE
          SET score = EXCLUDED.score,
              num_comments = EXCLUDED.num_comments,
              scraped_at = now()
        RETURNING id
        """,
        (
            post.reddit_post_id, post.permalink, post.title, post.subreddit,
            post.score, post.num_comments, post.posted_at, sentiment, ai_summary,
        ),
    ).fetchone()
    return row[0]


def upsert_item(
    conn: psycopg.Connection,
    listing: WeidianListing,
    translation: Translation,
    judge: JudgeResult,
) -> int:
    row = conn.execute(
        """
        INSERT INTO items
          (weidian_url, weidian_item_id, title_zh, title_en, description_en,
           brand, category, price_cny, seller_name, image_urls,
           status, last_validated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', now())
        ON CONFLICT (weidian_url) DO UPDATE
          SET status = 'active',
              dead_since = NULL,
              title_zh = EXCLUDED.title_zh,
              title_en = EXCLUDED.title_en,
              description_en = EXCLUDED.description_en,
              price_cny = EXCLUDED.price_cny,
              image_urls = EXCLUDED.image_urls,
              last_validated_at = now(),
              updated_at = now()
        RETURNING id
        """,
        (
            listing.weidian_url, listing.weidian_item_id, listing.title_zh,
            translation.title_en, translation.description_en,
            judge.brand, judge.category, listing.price_cny,
            listing.seller_name, json.dumps(listing.image_urls),
        ),
    ).fetchone()
    return row[0]


def link_mention(conn: psycopg.Connection, item_id: int, post_row_id: int) -> None:
    conn.execute(
        """
        INSERT INTO item_mentions (item_id, reddit_post_id)
        VALUES (%s, %s) ON CONFLICT DO NOTHING
        """,
        (item_id, post_row_id),
    )


def get_items_for_validation(conn: psycopg.Connection) -> list[tuple[int, str, str]]:
    return conn.execute(
        "SELECT id, weidian_url, status FROM items ORDER BY id"
    ).fetchall()


def set_item_status(conn: psycopg.Connection, item_id: int, status: str) -> None:
    if status == "inactive":
        conn.execute(
            """
            UPDATE items SET status='inactive', dead_since=now(),
                   last_validated_at=now(), updated_at=now()
            WHERE id=%s
            """,
            (item_id,),
        )
    else:
        conn.execute(
            """
            UPDATE items SET status='active', dead_since=NULL,
                   last_validated_at=now(), updated_at=now()
            WHERE id=%s
            """,
            (item_id,),
        )


def touch_validated(conn: psycopg.Connection, item_id: int) -> None:
    conn.execute("UPDATE items SET last_validated_at=now() WHERE id=%s", (item_id,))


def record_run(
    conn: psycopg.Connection,
    started_at: datetime,
    posts_seen: int,
    items_added: int,
    items_deactivated: int,
    error: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO scrape_runs
          (started_at, finished_at, posts_seen, items_added, items_deactivated, error)
        VALUES (%s, now(), %s, %s, %s, %s)
        """,
        (started_at, posts_seen, items_added, items_deactivated, error),
    )
```

- [ ] **Step 5: Run tests, expect pass**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest tests/test_db.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scraper/scraper/db.py scraper/tests/conftest.py scraper/tests/test_db.py
git commit -m "feat: scraper db layer with upserts and status transitions"
```

---

### Task 9: Revalidation

**Files:**
- Create: `scraper/scraper/revalidate.py`
- Test: `scraper/tests/test_revalidate.py`

**Interfaces:**
- Consumes: `Liveness`, `detect_liveness`, `fetch_lightweight`, `fetch_rendered` from `scraper.weidian`; `get_items_for_validation`, `set_item_status`, `touch_validated` from `scraper.db`
- Produces: `decide_status(liveness: Liveness, current_status: str) -> str | None` (None = no change); `check_liveness(url: str, fetch=fetch_lightweight, render=fetch_rendered) -> Liveness` (escalates UNKNOWN to Playwright; any exception → UNKNOWN); `revalidate_all(conn, fetch=..., render=...) -> int` (returns count deactivated). Used by Task 10.

- [ ] **Step 1: Write failing tests**

`scraper/tests/test_revalidate.py`:
```python
from scraper.revalidate import check_liveness, decide_status, revalidate_all
from scraper.weidian import Liveness
from tests.conftest import requires_db

DEAD_HTML = "<html><body>商品已下架</body></html>"
LIVE_HTML = '<html><head><meta property="og:title" content="帽衫"/></head><body></body></html>'


def test_decide_status():
    assert decide_status(Liveness.DEAD, "active") == "inactive"
    assert decide_status(Liveness.LIVE, "inactive") == "active"
    assert decide_status(Liveness.LIVE, "active") is None
    assert decide_status(Liveness.DEAD, "inactive") is None
    assert decide_status(Liveness.UNKNOWN, "active") is None
    assert decide_status(Liveness.UNKNOWN, "inactive") is None


def test_check_liveness_lightweight_dead():
    result = check_liveness("u", fetch=lambda u: (DEAD_HTML, 200), render=None)
    assert result is Liveness.DEAD


def test_check_liveness_escalates_to_render():
    calls = []

    def render(u):
        calls.append(u)
        return LIVE_HTML, 200

    result = check_liveness("u", fetch=lambda u: ("<html></html>", 200), render=render)
    assert result is Liveness.LIVE
    assert calls == ["u"]


def test_check_liveness_exception_is_unknown():
    def boom(u):
        raise TimeoutError("weidian slow")

    assert check_liveness("u", fetch=boom, render=boom) is Liveness.UNKNOWN


@requires_db
def test_revalidate_all_deactivates_and_revives(conn):
    from scraper import db
    from scraper.models import JudgeResult, Translation, WeidianListing

    def make(url):
        return WeidianListing(url, None, "t", "", None, None, [])

    t = Translation("t", "")
    j = JudgeResult(True, [], None, None, None, "")
    dead_id = db.upsert_item(conn, make("https://weidian.com/item.html?itemID=1"), t, j)
    live_id = db.upsert_item(conn, make("https://weidian.com/item.html?itemID=2"), t, j)
    db.set_item_status(conn, live_id, "inactive")  # will revive

    def fetch(url):
        return (DEAD_HTML, 200) if "itemID=1" in url else (LIVE_HTML, 200)

    deactivated = revalidate_all(conn, fetch=fetch, render=fetch)
    assert deactivated == 1
    statuses = dict(
        (r[0], r[2]) for r in db.get_items_for_validation(conn)
    )
    assert statuses[dead_id] == "inactive"
    assert statuses[live_id] == "active"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest tests/test_revalidate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`scraper/scraper/revalidate.py`:
```python
import logging

from . import db
from .weidian import Liveness, detect_liveness, fetch_lightweight, fetch_rendered

logger = logging.getLogger(__name__)


def decide_status(liveness: Liveness, current_status: str) -> str | None:
    if liveness is Liveness.DEAD and current_status == "active":
        return "inactive"
    if liveness is Liveness.LIVE and current_status == "inactive":
        return "active"
    return None


def check_liveness(url: str, fetch=fetch_lightweight, render=fetch_rendered) -> Liveness:
    try:
        html, status = fetch(url)
        liveness = detect_liveness(html, status)
        if liveness is Liveness.UNKNOWN and render is not None:
            html, status = render(url)
            liveness = detect_liveness(html, status)
        return liveness
    except Exception:
        logger.warning("liveness check failed for %s; leaving status unchanged", url, exc_info=True)
        return Liveness.UNKNOWN


def revalidate_all(conn, fetch=fetch_lightweight, render=fetch_rendered) -> int:
    deactivated = 0
    for item_id, url, current_status in db.get_items_for_validation(conn):
        liveness = check_liveness(url, fetch=fetch, render=render)
        new_status = decide_status(liveness, current_status)
        if new_status == "inactive":
            deactivated += 1
        if new_status is not None:
            db.set_item_status(conn, item_id, new_status)
        elif liveness is not Liveness.UNKNOWN:
            db.touch_validated(conn, item_id)
    return deactivated
```

- [ ] **Step 4: Run tests, expect pass**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest tests/test_revalidate.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/revalidate.py scraper/tests/test_revalidate.py
git commit -m "feat: daily revalidation with conservative deactivation"
```

---

### Task 10: Pipeline orchestrator + CLI

**Files:**
- Create: `scraper/scraper/run.py`, `scraper/scraper/__main__.py`
- Test: `scraper/tests/test_run.py`

**Interfaces:**
- Consumes: everything from Tasks 3–9
- Produces: `run_pipeline(conn, deps: Deps, limit: int | None = None) -> RunStats`; dataclasses `Deps` (injectable callables: `discover`, `fetch_comments`, `judge`, `fetch_page`, `translate`, `revalidate`) and `RunStats(posts_seen, items_added, items_deactivated)`. CLI: `python -m scraper.run --limit 5` (also `python -m scraper`). Reads `DATABASE_URL` and `ANTHROPIC_API_KEY` from env.

- [ ] **Step 1: Write failing tests**

`scraper/tests/test_run.py`:
```python
from scraper.models import JudgeResult, RedditPost, Translation
from scraper.run import Deps, run_pipeline
from tests.conftest import requires_db

pytestmark = requires_db

LIVE_HTML = (
    '<html><head><meta property="og:title" content="帽衫"/>'
    '<meta property="og:description" content="重磅"/>'
    '<meta property="og:image" content="https://si.geilicdn.com/a.jpg"/></head><body></body></html>'
)


def make_post(pid, body, score=100):
    return RedditPost(
        reddit_post_id=pid, permalink=f"https://reddit.com/{pid}", title=f"post {pid}",
        body=body, subreddit="FashionReps", score=score, num_comments=1, posted_at=1752300000,
    )


def make_deps(posts, judge_result):
    return Deps(
        discover=lambda: posts,
        fetch_comments=lambda post: ["nice quality"],
        judge=lambda post: judge_result,
        fetch_page=lambda url: (LIVE_HTML, 200),
        translate=lambda listing: Translation("CH hoodie", "heavy fabric"),
        revalidate=lambda conn: 0,
    )


def test_positive_post_creates_item(conn):
    posts = [make_post("p1", "https://weidian.com/item.html?itemID=111")]
    judge = JudgeResult(True, [], "Chrome Hearts", "clothing", "hoodie", "good")
    stats = run_pipeline(conn, make_deps(posts, judge))
    assert stats.posts_seen == 1
    assert stats.items_added == 1
    row = conn.execute("SELECT title_en, status FROM items").fetchone()
    assert row == ("CH hoodie", "active")
    assert conn.execute("SELECT count(*) FROM item_mentions").fetchone()[0] == 1


def test_negative_post_records_post_but_no_item(conn):
    posts = [make_post("p2", "https://weidian.com/item.html?itemID=222")]
    judge = JudgeResult(False, [], None, None, None, "shilly")
    stats = run_pipeline(conn, make_deps(posts, judge))
    assert stats.items_added == 0
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] == "negative"
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 0


def test_red_flagged_post_marked_flagged(conn):
    posts = [make_post("p3", "https://weidian.com/item.html?itemID=333")]
    judge = JudgeResult(True, ["known shill"], None, None, None, "")
    run_pipeline(conn, make_deps(posts, judge))
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] == "flagged"


def test_post_without_weidian_link_recorded_and_skipped(conn):
    posts = [make_post("p4", "just haul pics")]
    deps = make_deps(posts, JudgeResult(True, [], None, None, None, ""))
    deps.judge = lambda post: (_ for _ in ()).throw(AssertionError("judge must not be called"))
    stats = run_pipeline(conn, deps)
    assert stats.items_added == 0
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] is None


def test_already_seen_posts_skipped(conn):
    posts = [make_post("p5", "https://weidian.com/item.html?itemID=555")]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    run_pipeline(conn, make_deps(posts, judge))
    stats = run_pipeline(conn, make_deps(posts, judge))  # second run, same post
    assert stats.items_added == 0
    assert conn.execute("SELECT count(*) FROM reddit_posts").fetchone()[0] == 1


def test_one_bad_item_does_not_kill_run(conn):
    posts = [
        make_post("p6", "https://weidian.com/item.html?itemID=666"),
        make_post("p7", "https://weidian.com/item.html?itemID=777"),
    ]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    deps = make_deps(posts, judge)

    def flaky_fetch(url):
        if "666" in url:
            raise TimeoutError("weidian down")
        return LIVE_HTML, 200

    deps.fetch_page = flaky_fetch
    stats = run_pipeline(conn, deps)
    assert stats.items_added == 1


def test_limit_caps_candidate_posts(conn):
    posts = [
        make_post(f"p{i}", f"https://weidian.com/item.html?itemID=10{i}") for i in range(10)
    ]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    stats = run_pipeline(conn, make_deps(posts, judge), limit=3)
    assert stats.items_added == 3


def test_run_recorded(conn):
    posts = [make_post("p8", "https://weidian.com/item.html?itemID=888")]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    run_pipeline(conn, make_deps(posts, judge))
    row = conn.execute(
        "SELECT posts_seen, items_added, items_deactivated, error FROM scrape_runs"
    ).fetchone()
    assert row == (1, 1, 0, None)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`scraper/scraper/run.py`:
```python
import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from . import db
from .models import RedditPost, Translation, WeidianListing
from .weidian import Liveness, detect_liveness, parse_listing_html

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    discover: Callable[[], list[RedditPost]]
    fetch_comments: Callable[[RedditPost], list[str]]
    judge: Callable[[RedditPost], "JudgeResult"]
    fetch_page: Callable[[str], tuple[str, int]]
    translate: Callable[[WeidianListing], Translation]
    revalidate: Callable[..., int]


@dataclass
class RunStats:
    posts_seen: int = 0
    items_added: int = 0
    items_deactivated: int = 0


def _ingest_item(conn, deps: Deps, url: str, judge_result, post_row_id: int) -> bool:
    html, status = deps.fetch_page(url)
    if detect_liveness(html, status) is not Liveness.LIVE:
        logger.info("skipping %s: not live at ingest", url)
        return False
    listing = parse_listing_html(html, url)
    translation = deps.translate(listing)
    item_id = db.upsert_item(conn, listing, translation, judge_result)
    db.link_mention(conn, item_id, post_row_id)
    return True


def run_pipeline(conn, deps: Deps, limit: int | None = None) -> RunStats:
    from .extract import extract_weidian_urls
    from .judge import should_ingest

    started_at = datetime.now(timezone.utc)
    stats = RunStats()
    error: str | None = None
    try:
        posts = deps.discover()
        seen = db.seen_post_ids(conn, [p.reddit_post_id for p in posts])
        new_posts = [p for p in posts if p.reddit_post_id not in seen]
        stats.posts_seen = len(new_posts)

        processed = 0
        for post in new_posts:
            if limit is not None and processed >= limit:
                break
            try:
                post.comments = deps.fetch_comments(post)
                text = "\n".join([post.title, post.body, *post.comments])
                urls = extract_weidian_urls(text)
                if not urls:
                    db.insert_post(conn, post, None, None)
                    continue
                processed += 1
                judge_result = deps.judge(post)
                if judge_result.red_flags:
                    sentiment = "flagged"
                elif judge_result.positive_sentiment:
                    sentiment = "positive"
                else:
                    sentiment = "negative"
                post_row_id = db.insert_post(conn, post, sentiment, judge_result.quality_summary)
                if not should_ingest(judge_result):
                    continue
                for url in urls:
                    try:
                        if _ingest_item(conn, deps, url, judge_result, post_row_id):
                            stats.items_added += 1
                    except Exception:
                        logger.warning("failed to ingest %s", url, exc_info=True)
            except Exception:
                logger.warning("failed to process post %s", post.reddit_post_id, exc_info=True)

        stats.items_deactivated = deps.revalidate(conn)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.error("pipeline aborted", exc_info=True)
        raise
    finally:
        db.record_run(
            conn, started_at, stats.posts_seen, stats.items_added,
            stats.items_deactivated, error,
        )
    return stats


def build_default_deps() -> Deps:
    import anthropic
    import httpx

    from . import judge as judge_mod
    from . import reddit, revalidate, translate as translate_mod
    from .weidian import fetch_rendered

    http_client = httpx.Client()
    llm = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    return Deps(
        discover=lambda: reddit.discover_posts(http_client),
        fetch_comments=lambda post: reddit.fetch_post_comments(http_client, post),
        judge=lambda post: judge_mod.judge_post(llm, post),
        fetch_page=fetch_rendered,
        translate=lambda listing: translate_mod.translate_listing(llm, listing),
        revalidate=revalidate.revalidate_all,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="rep-nice-page daily pipeline")
    parser.add_argument("--limit", type=int, default=None, help="max candidate posts to process")
    args = parser.parse_args()

    conn = db.get_conn(os.environ["DATABASE_URL"])
    stats = run_pipeline(conn, build_default_deps(), limit=args.limit)
    logger.info(
        "done: %s new posts seen, %s items added, %s deactivated",
        stats.posts_seen, stats.items_added, stats.items_deactivated,
    )


if __name__ == "__main__":
    main()
```

`scraper/scraper/__main__.py`:
```python
from .run import main

main()
```

- [ ] **Step 4: Run tests, expect pass**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest -v`
Expected: full suite passes (all tasks so far), no failures.

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/run.py scraper/scraper/__main__.py scraper/tests/test_run.py
git commit -m "feat: pipeline orchestrator with per-item error isolation and --limit"
```

---

### Task 11: Web queries + Superbuy helper

**Files:**
- Create: `web/src/lib/superbuy.ts`, `web/src/lib/format.ts`, `web/src/db/queries.ts`
- Create: `web/vitest.config.ts`, `web/tests/setup.ts`
- Test: `web/tests/superbuy.test.ts`, `web/tests/queries.test.ts`

**Interfaces:**
- Consumes: `db` client and schema tables from Task 2
- Produces:
  - `superbuyUrl(weidianUrl: string): string`
  - `cnyToUsd(cny: number): number` and `CNY_TO_USD = 0.14` in `format.ts`
  - `getItems(opts: { category?: string; brand?: string; sort?: "trending" | "newest" | "price" }): Promise<ItemCardData[]>` where `ItemCardData = { id, titleEn, brand, category, priceCny, imageUrls, mentionCount, trendScore }`
  - `getItemDetail(id: number): Promise<ItemDetail | null>` where `ItemDetail` adds `descriptionEn, weidianUrl, sellerName, mentions: { permalink, title, score, aiSummary }[]`
  - `getFilterOptions(): Promise<{ brands: string[]; categories: string[] }>`

  Used by Task 12 pages.

- [ ] **Step 1: Write vitest config + failing superbuy test**

`web/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    setupFiles: ["./tests/setup.ts"],
  },
});
```

`web/tests/setup.ts`:
```typescript
import "dotenv/config";

if (process.env.TEST_DATABASE_URL) {
  process.env.DATABASE_URL = process.env.TEST_DATABASE_URL;
}
```

`web/tests/superbuy.test.ts`:
```typescript
import { describe, expect, it } from "vitest";
import { superbuyUrl } from "../src/lib/superbuy";
import { cnyToUsd } from "../src/lib/format";

describe("superbuyUrl", () => {
  it("wraps and encodes the weidian url", () => {
    expect(superbuyUrl("https://weidian.com/item.html?itemID=123")).toBe(
      "https://www.superbuy.com/en/page/buy/?url=https%3A%2F%2Fweidian.com%2Fitem.html%3FitemID%3D123",
    );
  });
});

describe("cnyToUsd", () => {
  it("converts with the fixed rate", () => {
    expect(cnyToUsd(100)).toBeCloseTo(14);
  });
});
```

Add to `web/package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run tests/superbuy.test.ts`
Expected: FAIL — cannot resolve `../src/lib/superbuy`

- [ ] **Step 3: Implement helpers**

`web/src/lib/superbuy.ts`:
```typescript
export function superbuyUrl(weidianUrl: string): string {
  return `https://www.superbuy.com/en/page/buy/?url=${encodeURIComponent(weidianUrl)}`;
}
```

`web/src/lib/format.ts`:
```typescript
export const CNY_TO_USD = 0.14; // rough fixed rate; update occasionally

export function cnyToUsd(cny: number): number {
  return cny * CNY_TO_USD;
}
```

Run: `cd web && npx vitest run tests/superbuy.test.ts` — Expected: 2 passed

- [ ] **Step 4: Write failing query tests**

`web/tests/queries.test.ts`:
```typescript
import { beforeEach, describe, expect, it } from "vitest";

const hasDb = !!process.env.TEST_DATABASE_URL;

describe.skipIf(!hasDb)("queries", () => {
  let db: typeof import("../src/db/client").db;
  let schema: typeof import("../src/db/schema");
  let queries: typeof import("../src/db/queries");

  beforeEach(async () => {
    db = (await import("../src/db/client")).db;
    schema = await import("../src/db/schema");
    queries = await import("../src/db/queries");
    await db.delete(schema.itemMentions);
    await db.delete(schema.items);
    await db.delete(schema.redditPosts);

    const [hot] = await db
      .insert(schema.items)
      .values({ weidianUrl: "https://weidian.com/item.html?itemID=1", titleEn: "hot hoodie", brand: "CH", category: "clothing", priceCny: "268", status: "active", imageUrls: [] })
      .returning();
    const [cold] = await db
      .insert(schema.items)
      .values({ weidianUrl: "https://weidian.com/item.html?itemID=2", titleEn: "cold ring", brand: "VW", category: "jewelry", priceCny: "80", status: "active", imageUrls: [] })
      .returning();
    await db
      .insert(schema.items)
      .values({ weidianUrl: "https://weidian.com/item.html?itemID=3", titleEn: "dead item", status: "inactive", imageUrls: [] });

    const [p1] = await db
      .insert(schema.redditPosts)
      .values({ redditPostId: "a", permalink: "https://reddit.com/a", title: "review", score: 400, sentiment: "positive" })
      .returning();
    const [p2] = await db
      .insert(schema.redditPosts)
      .values({ redditPostId: "b", permalink: "https://reddit.com/b", title: "w2c", score: 50, sentiment: "positive" })
      .returning();
    await db.insert(schema.itemMentions).values([
      { itemId: hot.id, redditPostId: p1.id },
      { itemId: hot.id, redditPostId: p2.id },
      { itemId: cold.id, redditPostId: p2.id },
    ]);
  });

  it("never returns inactive items", async () => {
    const rows = await queries.getItems({});
    expect(rows.map((r) => r.titleEn)).not.toContain("dead item");
  });

  it("sorts by trending (mentions + summed scores) by default", async () => {
    const rows = await queries.getItems({ sort: "trending" });
    expect(rows[0].titleEn).toBe("hot hoodie"); // 2 mentions + 450 score
    expect(rows[0].mentionCount).toBe(2);
  });

  it("filters by category", async () => {
    const rows = await queries.getItems({ category: "jewelry" });
    expect(rows).toHaveLength(1);
    expect(rows[0].titleEn).toBe("cold ring");
  });

  it("item detail includes mentions, inactive detail returns null-ish for public", async () => {
    const rows = await queries.getItems({});
    const detail = await queries.getItemDetail(rows[0].id);
    expect(detail).not.toBeNull();
    expect(detail!.mentions.length).toBeGreaterThan(0);
    expect(detail!.mentions[0].permalink).toContain("reddit.com");
  });

  it("filter options come from active items only", async () => {
    const opts = await queries.getFilterOptions();
    expect(opts.brands.sort()).toEqual(["CH", "VW"]);
    expect(opts.categories.sort()).toEqual(["clothing", "jewelry"]);
  });
});
```

Run: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run tests/queries.test.ts`
Expected: FAIL — cannot resolve `../src/db/queries`
(Also confirm skip works: `npx vitest run tests/queries.test.ts` without env → skipped.)
Note: apply migrations to the test DB first: `cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx drizzle-kit migrate`

- [ ] **Step 5: Implement queries**

`web/src/db/queries.ts`:
```typescript
import { and, desc, eq, isNotNull, sql } from "drizzle-orm";
import { db } from "./client";
import { itemMentions, items, redditPosts } from "./schema";

export type SortKey = "trending" | "newest" | "price";

export type ItemCardData = {
  id: number;
  titleEn: string | null;
  brand: string | null;
  category: string | null;
  priceCny: string | null;
  imageUrls: string[] | null;
  mentionCount: number;
  trendScore: number;
};

export type ItemDetail = ItemCardData & {
  descriptionEn: string | null;
  weidianUrl: string;
  sellerName: string | null;
  mentions: {
    permalink: string | null;
    title: string | null;
    score: number | null;
    aiSummary: string | null;
  }[];
};

const mentionCount = sql<number>`count(${itemMentions.redditPostId})::int`;
const trendScore = sql<number>`(count(${itemMentions.redditPostId}) + coalesce(sum(${redditPosts.score}), 0))::int`;

export async function getItems(opts: {
  category?: string;
  brand?: string;
  sort?: SortKey;
}): Promise<ItemCardData[]> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));

  const orderBy =
    opts.sort === "newest"
      ? desc(items.createdAt)
      : opts.sort === "price"
        ? sql`${items.priceCny} asc nulls last`
        : desc(trendScore);

  return db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(...filters))
    .groupBy(items.id)
    .orderBy(orderBy);
}

export async function getItemDetail(id: number): Promise<ItemDetail | null> {
  const [row] = await db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      descriptionEn: items.descriptionEn,
      weidianUrl: items.weidianUrl,
      sellerName: items.sellerName,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(eq(items.id, id), eq(items.status, "active")))
    .groupBy(items.id);

  if (!row) return null;

  const mentions = await db
    .select({
      permalink: redditPosts.permalink,
      title: redditPosts.title,
      score: redditPosts.score,
      aiSummary: redditPosts.aiSummary,
    })
    .from(itemMentions)
    .innerJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(eq(itemMentions.itemId, id))
    .orderBy(desc(redditPosts.score));

  return { ...row, mentions };
}

export async function getFilterOptions(): Promise<{ brands: string[]; categories: string[] }> {
  const brands = await db
    .selectDistinct({ v: items.brand })
    .from(items)
    .where(and(eq(items.status, "active"), isNotNull(items.brand)));
  const categories = await db
    .selectDistinct({ v: items.category })
    .from(items)
    .where(and(eq(items.status, "active"), isNotNull(items.category)));
  return {
    brands: brands.map((r) => r.v!).sort(),
    categories: categories.map((r) => r.v!).sort(),
  };
}
```

- [ ] **Step 6: Run tests, expect pass**

Run: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run`
Expected: superbuy 2 passed, queries 5 passed

- [ ] **Step 7: Commit**

```bash
git add web/src/lib web/src/db/queries.ts web/tests web/vitest.config.ts web/package.json
git commit -m "feat: catalog queries, superbuy handoff, usd conversion"
```

---

### Task 12: Web pages — grid, filters, item detail

**Files:**
- Create: `web/src/components/ItemImage.tsx`, `web/src/components/ItemCard.tsx`, `web/src/components/FilterBar.tsx`
- Modify: `web/src/app/page.tsx` (replace scaffold), `web/src/app/layout.tsx` (title/description only)
- Create: `web/src/app/item/[id]/page.tsx`
- Create: `web/public/placeholder.svg`

**Interfaces:**
- Consumes: `getItems`, `getItemDetail`, `getFilterOptions`, `ItemCardData` from Task 11; `superbuyUrl`, `cnyToUsd` from Task 11
- Produces: public pages `/` (grid with `?category=&brand=&sort=` search params) and `/item/[id]`. No new programmatic interfaces.

- [ ] **Step 1: Placeholder + image component**

`web/public/placeholder.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#e5e7eb"/><text x="200" y="200" font-family="sans-serif" font-size="20" fill="#9ca3af" text-anchor="middle" dominant-baseline="middle">image unavailable</text></svg>
```

`web/src/components/ItemImage.tsx` (client component — hotlinked with fallback):
```tsx
"use client";

import { useState } from "react";

export function ItemImage({ src, alt, className }: { src: string | null; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  const effective = !src || failed ? "/placeholder.svg" : src;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={effective}
      alt={alt}
      className={className}
      referrerPolicy="no-referrer"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
```

- [ ] **Step 2: Card + filter bar**

`web/src/components/ItemCard.tsx`:
```tsx
import Link from "next/link";
import type { ItemCardData } from "@/db/queries";
import { cnyToUsd } from "@/lib/format";
import { ItemImage } from "./ItemImage";

export function ItemCard({ item }: { item: ItemCardData }) {
  const cover = item.imageUrls?.[0] ?? null;
  const price = item.priceCny ? Number(item.priceCny) : null;
  return (
    <Link
      href={`/item/${item.id}`}
      className="group rounded-xl border border-zinc-200 bg-white overflow-hidden hover:shadow-md transition-shadow"
    >
      <div className="aspect-square overflow-hidden bg-zinc-100">
        <ItemImage
          src={cover}
          alt={item.titleEn ?? "item"}
          className="h-full w-full object-cover group-hover:scale-105 transition-transform"
        />
      </div>
      <div className="p-3 space-y-1">
        {item.brand && (
          <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">
            {item.brand}
          </span>
        )}
        <h3 className="text-sm font-medium line-clamp-2">{item.titleEn ?? "Untitled"}</h3>
        <div className="flex items-baseline justify-between text-sm">
          {price !== null ? (
            <span>
              ¥{price.toFixed(0)}{" "}
              <span className="text-zinc-500">≈ ${cnyToUsd(price).toFixed(0)}</span>
            </span>
          ) : (
            <span className="text-zinc-400">price unknown</span>
          )}
          <span className="text-xs text-zinc-500">
            {item.mentionCount} post{item.mentionCount === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </Link>
  );
}
```

`web/src/components/FilterBar.tsx` (server component; filters are plain links):
```tsx
import Link from "next/link";

type Props = {
  brands: string[];
  categories: string[];
  current: { category?: string; brand?: string; sort?: string };
};

function buildHref(current: Props["current"], patch: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  const merged = { ...current, ...patch };
  for (const [k, v] of Object.entries(merged)) if (v) params.set(k, v);
  const qs = params.toString();
  return qs ? `/?${qs}` : "/";
}

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className={`rounded-full px-3 py-1 text-sm border ${
        active ? "bg-zinc-900 text-white border-zinc-900" : "border-zinc-300 hover:bg-zinc-100"
      }`}
    >
      {children}
    </Link>
  );
}

export function FilterBar({ brands, categories, current }: Props) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Sort</span>
        {(["trending", "newest", "price"] as const).map((s) => (
          <Chip key={s} href={buildHref(current, { sort: s })} active={(current.sort ?? "trending") === s}>
            {s}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Category</span>
        <Chip href={buildHref(current, { category: undefined })} active={!current.category}>all</Chip>
        {categories.map((c) => (
          <Chip key={c} href={buildHref(current, { category: c })} active={current.category === c}>
            {c}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Brand</span>
        <Chip href={buildHref(current, { brand: undefined })} active={!current.brand}>all</Chip>
        {brands.map((b) => (
          <Chip key={b} href={buildHref(current, { brand: b })} active={current.brand === b}>
            {b}
          </Chip>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Home page**

Replace `web/src/app/page.tsx`:
```tsx
import { FilterBar } from "@/components/FilterBar";
import { ItemCard } from "@/components/ItemCard";
import { getFilterOptions, getItems, type SortKey } from "@/db/queries";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ category?: string; brand?: string; sort?: string }>;

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const sort = (["trending", "newest", "price"].includes(params.sort ?? "") ? params.sort : "trending") as SortKey;
  const [itemList, filterOptions] = await Promise.all([
    getItems({ category: params.category, brand: params.brand, sort }),
    getFilterOptions(),
  ]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">rep nice page</h1>
        <p className="text-sm text-zinc-500">
          items trending on r/FashionReps, refreshed daily · dead listings removed automatically
        </p>
      </header>
      <FilterBar
        brands={filterOptions.brands}
        categories={filterOptions.categories}
        current={{ category: params.category, brand: params.brand, sort: params.sort }}
      />
      {itemList.length === 0 ? (
        <p className="text-zinc-500 py-16 text-center">No items yet — the scraper hasn&apos;t run.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {itemList.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
```

In `web/src/app/layout.tsx`, set metadata only:
```tsx
export const metadata: Metadata = {
  title: "rep nice page",
  description: "Replica fashion items trending on r/FashionReps, with Superbuy links",
};
```

- [ ] **Step 4: Item detail page**

`web/src/app/item/[id]/page.tsx`:
```tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import { ItemImage } from "@/components/ItemImage";
import { getItemDetail } from "@/db/queries";
import { cnyToUsd } from "@/lib/format";
import { superbuyUrl } from "@/lib/superbuy";

export const dynamic = "force-dynamic";

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isInteger(numericId)) notFound();
  const item = await getItemDetail(numericId);
  if (!item) notFound();

  const price = item.priceCny ? Number(item.priceCny) : null;
  const summary = item.mentions.find((m) => m.aiSummary)?.aiSummary;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">← back to all items</Link>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <div className="aspect-square rounded-xl overflow-hidden bg-zinc-100">
            <ItemImage src={item.imageUrls?.[0] ?? null} alt={item.titleEn ?? "item"} className="h-full w-full object-cover" />
          </div>
          {(item.imageUrls?.length ?? 0) > 1 && (
            <div className="grid grid-cols-4 gap-2">
              {item.imageUrls!.slice(1, 9).map((url) => (
                <div key={url} className="aspect-square rounded-lg overflow-hidden bg-zinc-100">
                  <ItemImage src={url} alt="" className="h-full w-full object-cover" />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {item.brand && <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">{item.brand}</span>}
          <h1 className="text-xl font-bold">{item.titleEn ?? "Untitled"}</h1>
          {price !== null && (
            <p className="text-lg">
              ¥{price.toFixed(0)} <span className="text-zinc-500 text-sm">≈ ${cnyToUsd(price).toFixed(0)} USD</span>
            </p>
          )}
          {item.sellerName && <p className="text-sm text-zinc-500">Seller: {item.sellerName}</p>}

          <a
            href={superbuyUrl(item.weidianUrl)}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-xl bg-zinc-900 text-white text-center py-3 font-medium hover:bg-zinc-700"
          >
            Buy via Superbuy →
          </a>
          <a
            href={item.weidianUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-xl border border-zinc-300 text-center py-2 text-sm hover:bg-zinc-50"
          >
            View original on Weidian
          </a>

          {item.descriptionEn && <p className="text-sm text-zinc-700 whitespace-pre-line">{item.descriptionEn}</p>}

          {summary && (
            <div className="rounded-xl bg-amber-50 border border-amber-200 p-3">
              <h2 className="text-xs font-semibold uppercase text-amber-700 mb-1">Community verdict (AI summary)</h2>
              <p className="text-sm text-amber-900">{summary}</p>
            </div>
          )}

          <div>
            <h2 className="text-xs font-semibold uppercase text-zinc-500 mb-2">
              Seen in {item.mentions.length} Reddit post{item.mentions.length === 1 ? "" : "s"}
            </h2>
            <ul className="space-y-1">
              {item.mentions.map((m) => (
                <li key={m.permalink}>
                  <a href={m.permalink ?? "#"} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline">
                    {m.title ?? m.permalink} <span className="text-zinc-400">({m.score ?? 0} pts)</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Verify build + tests**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: build succeeds. (`force-dynamic` pages must not be prerendered against a missing DB — build with `DATABASE_URL` set to the local test DB if next tries to connect: `DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npm run build`.)
Run: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run`
Expected: all web tests still pass.

- [ ] **Step 6: Manual visual check**

Seed one row and view:
```bash
psql postgresql://postgres:test@localhost:5433/postgres -c "INSERT INTO items (weidian_url, title_en, brand, category, price_cny, image_urls, status) VALUES ('https://weidian.com/item.html?itemID=42','Test hoodie','Chrome Hearts','clothing',268,'[]','active') ON CONFLICT DO NOTHING;"
cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npm run dev
```
Expected: `/` shows one card with placeholder image; clicking it opens the detail page; Superbuy button href contains `url=https%3A%2F%2Fweidian.com`.

- [ ] **Step 7: Commit**

```bash
git add web/src web/public
git commit -m "feat: catalog grid, filters, item detail with superbuy handoff"
```

---

### Task 13: Deployment — Dockerfile, Railway config, docs

**Files:**
- Create: `scraper/Dockerfile`
- Modify: `README.md` (full deploy + ops docs)

**Interfaces:**
- Consumes: everything
- Produces: deployable scraper image; documented Railway setup. No code interfaces.

- [ ] **Step 1: Scraper Dockerfile**

`scraper/Dockerfile`:
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scraper ./scraper

CMD ["python", "-m", "scraper.run"]
```

Verify locally: `cd scraper && docker build -t repnice-scraper . && docker run --rm repnice-scraper python -c "import scraper.run; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 2: README deploy docs**

Replace `README.md` with:
```markdown
# rep-nice-page

Public catalog of replica fashion items trending on r/FashionReps, enriched from Weidian (translated, photos), with one-click Superbuy handoff. Dead Weidian listings are removed automatically by daily revalidation.

## Layout

- `web/` — Next.js catalog site
- `scraper/` — Python daily pipeline (discover → judge → enrich → revalidate)
- `docs/superpowers/` — spec + implementation plan

## Railway setup (3 services, one project)

1. **Postgres** — add the Railway Postgres plugin. Copy `DATABASE_URL`.
2. **web** — service from this repo, root directory `web/`.
   - Env: `DATABASE_URL`
   - Build/start: Railway autodetects Next.js (`npm run build` / `npm start`).
3. **scraper** — service from this repo, root directory `scraper/` (Dockerfile detected).
   - Env: `DATABASE_URL`, `ANTHROPIC_API_KEY`
   - Settings → Cron Schedule: `0 9 * * *` (daily 09:00 UTC). Restart policy: Never.

Apply migrations once (and after schema changes):

    cd web && DATABASE_URL=<railway url> npx drizzle-kit migrate

## Local development

    docker run -d --name repnice-test-pg -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:16
    cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx drizzle-kit migrate

- Web: `cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npm run dev`
- Scraper tests: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest`
- Web tests: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run`
- Pipeline smoke run (5 posts, real network + LLM):
  `cd scraper && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres ANTHROPIC_API_KEY=sk-... .venv/bin/python -m scraper.run --limit 5`

## Ops

- Did last night's run work? `SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 5;`
- An item wrongly deactivated revives automatically next run if its listing is live again.
```

- [ ] **Step 3: Full-suite verification**

Run: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest`
Expected: all pass.
Run: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add scraper/Dockerfile README.md
git commit -m "chore: scraper dockerfile and railway deploy docs"
```

---

## Post-plan verification (manual, before first deploy)

1. Run the real smoke pipeline: `python -m scraper.run --limit 5` against the local DB with a real `ANTHROPIC_API_KEY`. Inspect `items` rows — Weidian parsing selectors (`og:title`, price regex, geilicdn image regex) are the highest-risk guesses in this plan and may need adjustment against real Weidian HTML.
2. Open the local site, confirm real hotlinked images render (the `referrerPolicy="no-referrer"` trick) and Superbuy handoff opens the item.
3. Only then deploy to Railway.
