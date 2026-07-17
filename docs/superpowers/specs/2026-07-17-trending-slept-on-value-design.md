# Trending / Slept-on / Best-value — Design

**Date:** 2026-07-17
**Status:** Implemented (MVP)

## Motivation

Friend feedback: *"would loooove to see a 'trending items' and 'slept on' categories
— matching wicked price-to-material ratio, or surfing bleeding-edge social media fads."*

Those four phrases decompose into **2 new discovery pages** + **1 new sort signal**,
all built from data already in the schema. No migrations, no new dependencies.

## Features

### 1. `/trending` — "what's hot right now"
Distinct from the existing all-time "trending" *sort*: this page only counts Reddit
mentions from posts within a recency window, so a once-viral item from months ago
drops off.

- Window: `TRENDING_WINDOW_DAYS = 45` (tunable const in `queries.ts`; kept generous
  because the Reddit scrape runs weekly).
- Query `getTrending()`: items inner-joined to `item_mentions` → `reddit_posts` where
  `reddit_posts.posted_at > now() - 45d`, grouped by item, ranked by recent trend score
  (`count(mentions) + sum(post score)`). Paginated (`count(*) over()`).

### 2. `/slept-on` — "proven but unhyped"
- Heuristic: `seller_rebuy_rate` in the **top 30%** (percentile computed live via
  `percentile_cont(0.7)` so it self-tunes as the catalog grows) **AND** `sold >= 20`
  **AND** no Reddit mentions (`NOT EXISTS` against `item_mentions`).
- Query `getSleptOn()`: ordered by rebuy rate desc, then sold desc. Paginated.

### 3. "Best value" sort
- New `SortKey` value `"value"`, wired into `getItems`.
- Score: `rebuy_rate × ln(sold + 1) ÷ price_cny`, null-guarded so items missing
  price/sold/rebuy sink rather than error. A demand-per-yuan proxy — **not** true
  price-to-material (no material data exists yet; see backlog).

## UI

- **Routes:** `web/src/app/trending/page.tsx`, `web/src/app/slept-on/page.tsx` —
  `force-dynamic`, reuse `ItemCard` + `Pagination`, mirror the home grid.
- **Nav:** shared `NavLinks` component (Trending / Slept on / Vetted stores) in the
  header of home, stores, and both new pages, with an `active` highlight.
- **Sort control:** "Best value" added to `FilterBar`'s segmented control; `"value"`
  added to the sort whitelist in `page.tsx`.
- **Pagination:** gained a `basePath` prop (defaults `/`) so the new routes paginate
  against their own path.

## No migrations
Every signal already exists: `seller_rebuy_rate`, `sold`, `price_cny` on `items`;
`posted_at`/`score` on `reddit_posts`; `item_mentions` for hype presence.

## Future work / backlog
- **Social-media scraping** (TikTok / Instagram / Xiaohongshu) to surface genuinely
  bleeding-edge fads beyond weekly Reddit. New scraper per platform — large lift.
- **Real material/quality extraction** via an LLM pass over title+description
  (bolts onto the existing batched classify/translate passes; +1–2 cols, backfill)
  → a true price-to-material ratio replacing the current value proxy.
- **Trend velocity** (rising / accelerating) — rank by rate-of-change of mentions,
  and move the scrape weekly → daily for fresher signal.
- **Home preview shelves** — short rows on the home page linking into `/trending`
  and `/slept-on` (chose dedicated pages over shelves for the MVP).
