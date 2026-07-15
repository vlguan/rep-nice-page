# Spreadsheet Ingestion + Product Search — Design

**Date:** 2026-07-15
**Extends:** `2026-07-13-rep-nice-page-design.md`

## Decisions

| Decision | Choice |
|---|---|
| Spreadsheet source | Auto-discovered Google-Sheets links in scraped r/FashionReps posts/comments (no curated list) |
| Row handling | Staging table + budgeted promotion into `items`; all rows enriched |
| Weidian rows | Existing live-fetch → liveness → translate/classify path |
| Taobao rows | Enriched from the sheet's own data (name/price/image); no Taobao page scraping (login-walled) and no official API (key not obtainable) |
| Trust model | Spreadsheet rows bypass the sentiment judge — the sheet's community curation is the signal |
| Search | Fuzzy keyword search (pg_trgm) over active items AND unpromoted staging rows |
| Quick scrape | Search auto-flags top matching staging rows; an **always-on worker** enriches them within ~15–30s |
| Deployment | Scraper Railway service changes from cron to always-on worker (internal daily schedule + 10s promotion polling) |

## 1. Schema (one Drizzle migration, owned by `web/`)

- `items`: add `platform text NOT NULL DEFAULT 'weidian'` (`weidian` \| `taobao`); rename `weidian_url` → `product_url`, `weidian_item_id` → `platform_item_id`. All web queries and scraper SQL updated.
- `spreadsheets`: `id`, `sheet_key` (Google sheet ID, unique), `url`, `title`, `discovered_post_id` (FK `reddit_posts`, nullable), `discovered_at`, `last_synced_at`, `sync_error`, `status` (`active` \| `gone`).
- `spreadsheet_rows` (staging): `id`, `spreadsheet_id` FK, `tab_name`, `row_number`, `name`, `price_raw`, `currency`, `image_url`, `raw_link`, `product_url` (canonical, nullable), `platform`, `item_id` (FK `items`, null until promoted), `requested_at` (search-priority flag), `promote_error`, `created_at`. Unique `(spreadsheet_id, tab_name, row_number)`; re-sync upserts on that key.
- `item_spreadsheet_mentions`: `item_id` FK, `spreadsheet_id` FK, unique pair.
- Enable `pg_trgm`; GIN trigram indexes on `items.title_en`, `items.brand`, `spreadsheet_rows.name`.
- One-off cleanup in the migration window (manual SQL, not migration): delete orphaned items with zero mentions (local test artifacts).

## 2. Sheet discovery (scraper, discover stage)

- `extract.extract_sheet_keys(text)`: regex `docs.google.com/spreadsheets/d/<key>`.
- Runs on title/body/comments of every examined post **before** the no-Weidian-URLs skip (sheet posts often carry no direct item links). New sheet keys upsert into `spreadsheets`.

## 3. Sheet sync (scraper)

- Download whole workbook via public `https://docs.google.com/spreadsheets/d/<key>/export?format=xlsx` (httpx, no API key). 403/404/timeouts → record `sync_error`; repeated permanent failures → `status='gone'`. Parse with `openpyxl`.
- Per tab: one Haiku call maps columns from the first 10 rows → `{name_col, price_col, link_col, image_col, currency}` or `not_items` (skip tab). Row parsing after that is mechanical (no per-row LLM).
- Agent-link unwrapping: CNFans / ACBuy / Mulebuy / AllChinaBuy / Superbuy / Kakobuy wrappers (`url=` param or `id=` + `platform=` forms) → canonical Weidian (`weidian.com/item.html?itemID=`) or Taobao (`item.taobao.com/item.htm?id=`) URL. Rows without a resolvable product link are stored with `product_url=NULL` (searchable, never promoted).
- Caps: 20 tabs/sheet, 2,000 rows/tab. Re-sync each active sheet when `last_synced_at` > 7 days.
- Rows whose `product_url` already exists in `items` are linked immediately (`item_id` set + `item_spreadsheet_mentions`), no re-enrichment.

## 4. Promotion (scraper, new pipeline stage)

- Budget per daily run: 200 rows. Order: `requested_at IS NOT NULL` first (oldest request first), then newest rows.
- Weidian rows: existing fetch → liveness gate → translate/classify (sheet row name passed as classification context alongside any Reddit context).
- Taobao rows: item built from sheet data — `title_en`/brand/category from a translate/classify call on the row name, price from sheet (CNY as-is; USD converted at the fixed rate constant; unknown currency → NULL), image from sheet. `last_validated_at` NULL.
- On success: `item_id` set on the row + `item_spreadsheet_mentions` link. On failure: `promote_error` recorded, row skipped (no automatic retry).
- Trending rank on the site remains post-mention-count; spreadsheet-only items rank under "newest".

## 5. Revalidation changes

- Only `platform='weidian'` items are revalidated; Taobao items are never auto-deactivated.
- Scaling guard: revalidate only items with `last_validated_at` older than 7 days, capped at 500/run (existing mass-deactivation circuit breaker unchanged).

## 6. Worker mode (scraper deployment change)

- New entrypoint `python -m scraper.worker`:
  - every ~10s: promote any `requested_at`-flagged, unpromoted rows (small batch, e.g. 10);
  - once per day at 09:00 UTC (guarded by querying `scrape_runs` for today's run, restart-safe): full pipeline (discover → judge → ingest → sheet sync → promotion budget → revalidate).
- `python -m scraper.run` stays for manual runs.
- Railway: scraper service drops its cron schedule, restart policy `always`; Dockerfile CMD → worker.

## 7. Search (web)

- Search box in the catalog filter bar → `?q=`.
- Items query: `similarity(title_en, q)`-ranked with `ILIKE` fallback across `title_en`, `title_zh`, `brand`; active items only; combines with existing category/brand filters.
- Staging query: same fuzzy match on `spreadsheet_rows.name` where `item_id IS NULL`, rendered as a separate "From spreadsheets" section — card shows sheet name/price/image and a working Superbuy link (`product_url` known), labeled with the source sheet title.
- Quick scrape: each search fires an async, fire-and-forget `UPDATE` setting `requested_at=now()` on the top 5 matching unpromoted rows (with `product_url`). The worker enriches them within seconds; they appear as full catalog items on the next search/reload. No websockets/polling UI.

## 8. Error handling

- Sheet download/parse failures: per-sheet `sync_error`, never abort the run.
- Column-mapping LLM: 1 retry then skip tab (consistent with existing LLM guard).
- Promotion failures: per-row `promote_error`, never abort.
- Worker loop: exceptions logged, loop continues; daily-run guard prevents double runs after crash-restart.

## 9. Testing

- Unit: sheet-key extraction, agent-link unwrapping, column-mapping parse validation, xlsx tab parsing (fixture workbook), promotion ordering/budget, currency handling.
- DB (TEST_DATABASE_URL): staging upsert idempotency on re-sync, already-in-catalog linking, promotion writes + mentions, search queries (trigram match + staging section), requested_at flagging.
- Web (vitest): search query builder, staging-card Superbuy URL (platform-aware `WD`/`TB`).
