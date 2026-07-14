# rep-nice-page — Design Spec

**Date:** 2026-07-13
**Status:** Approved
**Goal:** Public website that automatically surfaces replica fashion items (clothing and jewelry) trending on r/FashionReps, enriched from their Weidian listings (translated, with photos), stored in Postgres, with one-click redirection to Superbuy. Dead Weidian listings disappear from the site automatically via daily revalidation.

---

## Decisions Made During Brainstorming

| Question | Decision |
|---|---|
| Audience | Public, shared with friends |
| Ingestion | Fully automated — no manual review queue |
| Product scope | Whatever is trending on r/FashionReps top/hot; clothing + jewelry (not brand-limited) |
| Hosting | Railway: web service + Postgres service + scraper cron service |
| Images | Hotlink Weidian image URLs directly, `onerror` placeholder fallback; schema keeps room for mirroring later |
| Dead listings | Daily revalidation; dead items flip to `inactive` and are filtered from all site queries |
| Reddit access | Public JSON API (`.json` endpoints), not HTML scraping — more reliable than Scrapling on Reddit HTML |
| Weidian access | Playwright headless browser (real bot detection exists there) |
| LLM | Anthropic API, Haiku 4.5 for judge + translation (cheap, sufficient) |
| Superbuy | Plain URL handoff `https://www.superbuy.com/en/page/buy/?url=<encoded weidian url>` — no API, no affiliate setup |

Prior art: `Documents/dev/taobaoscrapper/docs/superpowers/specs/2026-06-02-reddit-rep-jewelry-scraper-design.md` (never implemented). Its shill-detection tiers, Weidian URL regexes, and Chinese removal-notice detection are reused here.

---

## 1. Architecture

Monorepo `rep-nice-page/` with two deployed services plus Railway Postgres:

```
┌─────────────────────┐        ┌──────────────────────────┐
│ scraper (Python)    │        │ web (Next.js)            │
│ Railway cron, daily │ writes │ always-on service        │
│                     │───────▶│ reads Postgres,          │
│ discover → judge →  │  Postgres  renders item grid     │
│ enrich → revalidate │        │ + Superbuy redirect      │
└─────────────────────┘        └──────────────────────────┘
```

- The two services never communicate directly; Postgres is the only interface.
- One daily cron run performs ingest (new items) then revalidation (existing items), in that order.
- Repo layout:

```
rep-nice-page/
├── web/          # Next.js app (Railway service 1)
├── scraper/      # Python pipeline (Railway cron service 2, Dockerfile with Playwright)
└── docs/
```

## 2. Scraper Pipeline (Python)

Single entry point (`python -m scraper.run`), four sequential stages. Every stage is independent per item: a failure on one item logs and skips, never aborts the run.

### Stage 1 — Discover (Reddit JSON API)

- Fetch `https://old.reddit.com/r/FashionReps/top.json?t=week&limit=100` and `hot.json?limit=100`.
- For each post not already in `reddit_posts` (dedupe on Reddit post ID), fetch its comments JSON (top-level comments only).
- Extract Weidian URLs from post body + comments. Regex targets:
  - `weidian.com/item.html?itemID=`
  - `weidian.com/item/`, `weidian.com/items/`
  - Tracking params stripped; normalized to a canonical URL before dedupe.
- Posts with no Weidian URL are recorded (so they aren't refetched) and skipped.
- Politeness: honest User-Agent, backoff on HTTP 429. Unauthenticated JSON API allows ~100 req/10 min; a daily run stays under this with a small request delay.

### Stage 2 — Judge (Claude, one call per new candidate post)

Input: post title, body, top-level comments. Structured output:

```json
{
  "positive_sentiment": true,
  "red_flags": ["..."],
  "brand": "Chrome Hearts",
  "category": "jewelry",        // clothing | jewelry | shoes | accessory
  "item_name": "22k cross pendant",
  "quality_summary": "one-paragraph prose summary of genuine signals"
}
```

Judging tiers (from the taobaoscrapper spec, in precedence order):
1. **Community red flags** — explicit callouts ("nice try", "known shill", "buys reviews") override everything.
2. **Shill patterns** — generic praise, throwaway accounts, identical phrasing, no photos where photos are the norm.
3. **Genuine quality signals** — specific materials, stitching, weight, sizing accuracy, retail comparisons.

Only `positive_sentiment: true` with no tier-1 red flags proceeds. Model: `claude-haiku-4-5-20251001`. Responses validated against a schema; one retry on parse failure, then skip the post.

### Stage 3 — Enrich (Playwright + Claude)

- Load the Weidian item URL in headless Playwright.
- Scrape: Chinese title, Chinese description text, price (CNY), image URLs, seller name.
- If the page shows a removal notice ("商品已下架", "该店铺已关闭") or 404s: the item never enters the DB.
- One Claude call translates title + description to English.
- Upsert into `items` on `weidian_url`; link to the Reddit post via `item_mentions`. An item mentioned by five posts is one item with five mention rows.

### Stage 4 — Revalidate (daily, all active items)

- For every `items.status = 'active'` row: lightweight HTTP GET first; escalate to Playwright only if the response is ambiguous (e.g., JS-rendered shell).
- Confirmed dead (removal notice text or 404) → `status = 'inactive'`, `dead_since = now()`.
- Network error / timeout / rate limit → **no status change** (never deactivate on infrastructure failure), logged.
- An inactive item found alive again → back to `active`, `dead_since` cleared.

### Cost model

Claude calls happen only for never-before-seen posts that contain a Weidian link (judge) and for items entering the DB (translate) — typically a few dozen Haiku calls/day. Pennies.

## 3. Data Model (Postgres, Drizzle-managed schema)

```sql
items (
  id            serial PK,
  weidian_url   text UNIQUE NOT NULL,   -- canonical, tracking params stripped
  weidian_item_id text,
  title_zh      text,
  title_en      text,
  description_en text,
  brand         text,
  category      text,                    -- clothing | jewelry | shoes | accessory
  price_cny     numeric,
  seller_name   text,
  image_urls    jsonb,                   -- array; [0] is cover; hotlinked
  status        text NOT NULL DEFAULT 'active',  -- active | inactive
  last_validated_at timestamptz,
  dead_since    timestamptz,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
)

reddit_posts (
  id             serial PK,
  reddit_post_id text UNIQUE NOT NULL,
  permalink      text,
  title          text,
  subreddit      text,
  score          int,
  num_comments   int,
  posted_at      timestamptz,
  scraped_at     timestamptz,
  sentiment      text,                   -- positive | negative | flagged
  ai_summary     text                    -- quality_summary from judge
)

item_mentions (
  item_id        int FK → items,
  reddit_post_id int FK → reddit_posts,
  PRIMARY KEY (item_id, reddit_post_id)
)

scrape_runs (
  id                serial PK,
  started_at        timestamptz,
  finished_at       timestamptz,
  posts_seen        int,
  items_added       int,
  items_deactivated int,
  error             text                 -- non-null if the run aborted
)
```

"Trending" sort = mention count + summed Reddit scores of mentioning posts, computed in the query.

Schema is owned by Drizzle in `web/`; the Python scraper treats it as an external contract (plain SQL via psycopg, no second ORM migration source).

## 4. Web App (Next.js, Railway)

- **Home** — responsive card grid. Card: cover photo (hotlinked; `onerror` swaps a local placeholder), English title, brand chip, price in CNY + approximate USD (hardcoded-ish rate constant, updated rarely), mention count ("seen in 4 posts"). Sort: trending (default) / newest / price. Filter: category, brand.
- **Item detail** — photo strip, translated description, AI quality summary, links to source Reddit posts, original Weidian link, and the primary **"Buy via Superbuy"** button (URL handoff as above, `target="_blank"`).
- All queries filter `status = 'active'`. No auth, no accounts, read-only.
- Stack: App Router, server components, Drizzle ORM, Tailwind. No client state library.

## 5. Error Handling

- Per-item isolation in every pipeline stage; failures log and skip.
- Claude structured output validated; retry once, then skip.
- Reddit 429 → exponential backoff.
- Revalidation deactivates only on **confirmed** death (removal notice / 404), never on timeout or network error.
- Every run writes a `scrape_runs` row, including aborted runs (with `error` set) — this is the observability surface for "did last night's sync work?".
- Web: a broken hotlinked image is a UI concern only (placeholder); it does not affect item status. If an item's images consistently die while the listing is live, that's acceptable per the hotlinking decision.

## 6. Testing

- **Scraper (pytest, offline):** fixture files — recorded Reddit JSON payloads, saved Weidian HTML for live and removed listings. Tests cover URL extraction/normalization, dedupe, liveness detection, and judge/translate response parsing (Claude mocked with recorded responses).
- **Web:** integration tests that `inactive` items never render and filters/sorts produce correct SQL results against a test DB.
- **Manual smoke:** `python -m scraper.run --limit 5` runs a tiny real pipeline against live Reddit/Weidian before deploys.

## Out of Scope

- No manual review/admin queue (fully automated by decision)
- No image mirroring/storage (hotlink by decision; `image_urls` schema supports adding mirrored URLs later)
- No Taobao (Weidian only for v1)
- No price history, no user accounts, no favorites
- No Superbuy affiliate integration
- No translation of Weidian reviews (item title/description only)
