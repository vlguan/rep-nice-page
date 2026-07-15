# Spreadsheet Ingestion + Product Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-discover community W2C Google Sheets in scraped r/FashionReps posts, stage their rows in Postgres, promote rows into the catalog on a budget (search-triggered rows within seconds via an always-on worker), and add fuzzy product search over items + staged rows.

**Architecture:** Sheets are found by the existing discover stage, downloaded as XLSX via Google's public export endpoint, column-mapped once per tab by Haiku, and bulk-staged into `spreadsheet_rows`. A promotion stage enriches rows into `items` (Weidian via the live-fetch path; Taobao from sheet data). The scraper becomes an always-on worker (10s promotion polling + internal daily schedule). Web search uses pg_trgm over items and staged rows, and flags top staging matches for immediate promotion.

**Tech Stack:** Python 3.12, httpx, openpyxl, anthropic (Haiku), psycopg 3 · Next.js App Router, Drizzle, postgres.js · Postgres pg_trgm.

**Spec:** `docs/superpowers/specs/2026-07-15-spreadsheets-and-search-design.md`

## Global Constraints

- LLM model: `claude-haiku-4-5-20251001` (`scraper/scraper/config.py:MODEL`). Max 1 retry on unparseable LLM response, then skip.
- Canonical URLs: Weidian `https://weidian.com/item.html?itemID=<digits>`; Taobao `https://item.taobao.com/item.htm?id=<digits>`.
- `items.platform` values: `'weidian' | 'taobao'` only. Taobao items are NEVER auto-deactivated.
- Caps: 20 tabs/sheet, 2,000 rows/tab, 200 promoted rows per daily run, 10 rows per worker poll batch, top 5 rows flagged per search, sheets re-synced when `last_synced_at` older than 7 days, revalidation 500 items/run older than 7 days.
- Currency: sheet CNY used as-is; USD converted at `USD_TO_CNY = 7.14`; anything else → price NULL.
- Daily pipeline time: 09:00 UTC, restart-safe (guard on `scrape_runs` having a run started today).
- Spreadsheet rows bypass the sentiment judge (neutral JudgeResult).
- Scraper tests: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test .venv/bin/python -m pytest`. Web tests: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test npx vitest run`. DB tests auto-skip without `TEST_DATABASE_URL`.
- Commit after every green test cycle; conventional commit messages; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The scraper's Python venv is `scraper/.venv` (invoke as `.venv/bin/python`); web commands run from `web/`.

---

### Task 1: Schema migration + web rename plumbing

**Files:**
- Create: `web/drizzle/0001_spreadsheets_search.sql`
- Modify: `web/drizzle/meta/_journal.json`, `web/src/db/schema.ts`, `web/src/db/queries.ts`, `web/src/app/item/[id]/page.tsx`, `web/src/lib/superbuy.ts`, `web/tests/superbuy.test.ts`, `web/tests/queries.test.ts`

**Interfaces:**
- Produces (later tasks rely on): DB columns `items.product_url`, `items.platform_item_id`, `items.platform`; tables `spreadsheets`, `spreadsheet_rows`, `item_spreadsheet_mentions`; Drizzle exports `spreadsheets`, `spreadsheetRows`, `itemSpreadsheetMentions`; `superbuyUrl(productUrl: string, platform?: string, partnerCode?: string)`.

- [ ] **Step 1: Write the migration**

`web/drizzle/0001_spreadsheets_search.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
--> statement-breakpoint
ALTER TABLE "items" RENAME COLUMN "weidian_url" TO "product_url";
--> statement-breakpoint
ALTER TABLE "items" RENAME COLUMN "weidian_item_id" TO "platform_item_id";
--> statement-breakpoint
ALTER TABLE "items" ADD COLUMN "platform" text NOT NULL DEFAULT 'weidian';
--> statement-breakpoint
CREATE TABLE "spreadsheets" (
        "id" serial PRIMARY KEY NOT NULL,
        "sheet_key" text NOT NULL UNIQUE,
        "url" text NOT NULL,
        "title" text,
        "discovered_post_id" integer REFERENCES "reddit_posts"("id"),
        "discovered_at" timestamp with time zone DEFAULT now(),
        "last_synced_at" timestamp with time zone,
        "sync_error" text,
        "status" text NOT NULL DEFAULT 'active'
);
--> statement-breakpoint
CREATE TABLE "spreadsheet_rows" (
        "id" serial PRIMARY KEY NOT NULL,
        "spreadsheet_id" integer NOT NULL REFERENCES "spreadsheets"("id"),
        "tab_name" text NOT NULL,
        "row_number" integer NOT NULL,
        "name" text,
        "price_raw" text,
        "currency" text,
        "image_url" text,
        "raw_link" text,
        "product_url" text,
        "platform" text,
        "item_id" integer REFERENCES "items"("id"),
        "requested_at" timestamp with time zone,
        "promote_error" text,
        "created_at" timestamp with time zone DEFAULT now(),
        CONSTRAINT "spreadsheet_rows_sheet_tab_row_unique" UNIQUE("spreadsheet_id","tab_name","row_number")
);
--> statement-breakpoint
CREATE TABLE "item_spreadsheet_mentions" (
        "item_id" integer NOT NULL REFERENCES "items"("id"),
        "spreadsheet_id" integer NOT NULL REFERENCES "spreadsheets"("id"),
        CONSTRAINT "item_spreadsheet_mentions_pk" PRIMARY KEY("item_id","spreadsheet_id")
);
--> statement-breakpoint
CREATE INDEX "items_title_en_trgm" ON "items" USING gin ("title_en" gin_trgm_ops);
--> statement-breakpoint
CREATE INDEX "items_brand_trgm" ON "items" USING gin ("brand" gin_trgm_ops);
--> statement-breakpoint
CREATE INDEX "spreadsheet_rows_name_trgm" ON "spreadsheet_rows" USING gin ("name" gin_trgm_ops);
```

- [ ] **Step 2: Register it in the Drizzle journal**

In `web/drizzle/meta/_journal.json`, append to `entries` (keep the existing entry):

```json
{ "idx": 1, "version": "7", "when": 1752570000000, "tag": "0001_spreadsheets_search", "breakpoints": true }
```

(Note: we hand-write migrations rather than `drizzle-kit generate` because generate prompts interactively on renames.)

- [ ] **Step 3: Update `web/src/db/schema.ts`**

In `items`: replace the two renamed fields and add `platform`:

```ts
  productUrl: text("product_url").notNull().unique(),
  platformItemId: text("platform_item_id"),
  platform: text("platform").notNull().default("weidian"), // weidian | taobao
```

Append the new tables:

```ts
export const spreadsheets = pgTable("spreadsheets", {
  id: serial("id").primaryKey(),
  sheetKey: text("sheet_key").notNull().unique(),
  url: text("url").notNull(),
  title: text("title"),
  discoveredPostId: integer("discovered_post_id").references(() => redditPosts.id),
  discoveredAt: timestamp("discovered_at", { withTimezone: true }).defaultNow(),
  lastSyncedAt: timestamp("last_synced_at", { withTimezone: true }),
  syncError: text("sync_error"),
  status: text("status").notNull().default("active"), // active | gone
});

export const spreadsheetRows = pgTable(
  "spreadsheet_rows",
  {
    id: serial("id").primaryKey(),
    spreadsheetId: integer("spreadsheet_id").notNull().references(() => spreadsheets.id),
    tabName: text("tab_name").notNull(),
    rowNumber: integer("row_number").notNull(),
    name: text("name"),
    priceRaw: text("price_raw"),
    currency: text("currency"),
    imageUrl: text("image_url"),
    rawLink: text("raw_link"),
    productUrl: text("product_url"),
    platform: text("platform"),
    itemId: integer("item_id").references(() => items.id),
    requestedAt: timestamp("requested_at", { withTimezone: true }),
    promoteError: text("promote_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [unique("spreadsheet_rows_sheet_tab_row_unique").on(t.spreadsheetId, t.tabName, t.rowNumber)],
);

export const itemSpreadsheetMentions = pgTable(
  "item_spreadsheet_mentions",
  {
    itemId: integer("item_id").notNull().references(() => items.id),
    spreadsheetId: integer("spreadsheet_id").notNull().references(() => spreadsheets.id),
  },
  (t) => [primaryKey({ columns: [t.itemId, t.spreadsheetId] })],
);
```

Add `unique` to the drizzle-orm/pg-core import.

- [ ] **Step 4: Rename through web code**

- `web/src/db/queries.ts`: `weidianUrl: items.weidianUrl` → `productUrl: items.productUrl`; in `ItemDetail` type `weidianUrl: string` → `productUrl: string; platform: string`; add `platform: items.platform` to the detail select.
- `web/src/app/item/[id]/page.tsx`: `superbuyUrl(item.weidianUrl)` → `superbuyUrl(item.productUrl, item.platform)`.
- `web/src/lib/superbuy.ts` — platform-aware:

```ts
const WEIDIAN_ID = /[?&]itemID=(\d+)/i;
const TAOBAO_ID = /[?&]id=(\d+)/i;

export function superbuyUrl(
  productUrl: string,
  platform: string = "weidian",
  partnerCode: string | undefined = process.env.SUPERBUY_PARTNER_CODE,
): string {
  const idRe = platform === "taobao" ? TAOBAO_ID : WEIDIAN_ID;
  const platformCode = platform === "taobao" ? "TB" : "WD";
  const match = productUrl.match(idRe);
  if (!match) {
    return `https://www.superbuy.com/en/page/buy/?url=${encodeURIComponent(productUrl)}`;
  }
  // partnercode attributes new-user registrations from this handoff to our
  // affiliate account; trackPayload mirrors Superbuy's own share links.
  const partner = partnerCode ? `&partnercode=${partnerCode}&trackPayload=pc_share` : "";
  return `https://www.superbuy.com/en/page/buy/?platform=${platformCode}&id=${match[1]}${partner}`;
}
```

- [ ] **Step 5: Write the failing tests**

Append to `web/tests/superbuy.test.ts` inside the `describe("superbuyUrl")` block:

```ts
  it("builds a TB link for taobao items", () => {
    expect(superbuyUrl("https://item.taobao.com/item.htm?id=987", "taobao", "wcOcdG")).toBe(
      "https://www.superbuy.com/en/page/buy/?platform=TB&id=987&partnercode=wcOcdG&trackPayload=pc_share",
    );
  });
```

Update `web/tests/queries.test.ts`: every `weidianUrl:` fixture key → `productUrl:`; the `getItemDetail` assertion on `weidianUrl` → `productUrl`.

- [ ] **Step 6: Apply migration + run tests**

```bash
cd web
DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test npx drizzle-kit migrate
DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx drizzle-kit migrate
TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test npx vitest run
```

Expected: all vitest tests pass. (The scraper suite is temporarily broken by the rename — Task 2 fixes it; run only web tests here.)

- [ ] **Step 7: One-off catalog cleanup (orphaned local test artifacts)**

```bash
docker exec rep-nice-page-test-pg psql -U postgres -c "DELETE FROM items WHERE NOT EXISTS (SELECT 1 FROM item_mentions m WHERE m.item_id = items.id);"
```

- [ ] **Step 8: Commit**

```bash
git add web/drizzle web/src web/tests
git commit -m "feat: platform-aware items schema, spreadsheet tables, pg_trgm indexes"
```

---

### Task 2: Scraper rename plumbing + revalidation guard

**Files:**
- Modify: `scraper/scraper/db.py`, `scraper/scraper/config.py`
- Test: `scraper/tests/test_db.py` (adjust), `scraper/tests/test_revalidate.py` (adjust if column-dependent)

**Interfaces:**
- Consumes: Task 1 columns (`product_url`, `platform_item_id`, `platform`).
- Produces: `db.upsert_item` writing `platform='weidian'`; `db.get_items_for_validation(conn)` returning only weidian items due for revalidation (≤500, `last_validated_at` NULL-or-older-than-7-days first); `config.USD_TO_CNY = 7.14`.

- [ ] **Step 1: Run the scraper suite to see the rename breakage**

```bash
cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test .venv/bin/python -m pytest -q
```

Expected: DB-backed tests FAIL with `column "weidian_url" ... does not exist`.

- [ ] **Step 2: Update `scraper/scraper/db.py`**

In `upsert_item`, the INSERT column list becomes:

```sql
INSERT INTO items
  (product_url, platform_item_id, platform, title_zh, title_en, description_en,
   brand, category, price_cny, seller_name, image_urls,
   status, last_validated_at)
VALUES (%s, %s, 'weidian', %s, %s, %s, %s, %s, %s, %s, %s, 'active', now())
ON CONFLICT (product_url) DO UPDATE
```

(parameters tuple unchanged apart from no new values — `platform` is a literal). `get_items_for_validation` becomes:

```python
def get_items_for_validation(conn: psycopg.Connection) -> list[tuple[int, str, str]]:
    # Weidian only (taobao pages can't be checked); stale-first, capped so a
    # large catalog can't blow up the nightly run.
    return conn.execute(
        """
        SELECT id, product_url, status FROM items
        WHERE platform = 'weidian'
          AND (last_validated_at IS NULL OR last_validated_at < now() - interval '7 days')
        ORDER BY last_validated_at NULLS FIRST, id
        LIMIT 500
        """
    ).fetchall()
```

- [ ] **Step 3: Update `scraper/scraper/config.py`**

```python
USD_TO_CNY = 7.14  # sheet prices given in USD are stored as CNY at this rate
```

- [ ] **Step 4: Fix test fixtures that reference the old columns**

In `scraper/tests/test_db.py` and any test using raw SQL with `weidian_url`/`weidian_item_id`: rename to `product_url`/`platform_item_id`. In `scraper/tests/test_run.py` the SELECT `weidian_item_id` → `platform_item_id`. Add a revalidation-guard test to `scraper/tests/test_db.py`:

```python
def test_get_items_for_validation_skips_taobao_and_fresh(conn):
    conn.execute(
        "INSERT INTO items (product_url, platform, status, last_validated_at) VALUES"
        " ('https://item.taobao.com/item.htm?id=1', 'taobao', 'active', NULL),"
        " ('https://weidian.com/item.html?itemID=2', 'weidian', 'active', now()),"
        " ('https://weidian.com/item.html?itemID=3', 'weidian', 'active', now() - interval '8 days')"
    )
    rows = db.get_items_for_validation(conn)
    assert [r[1] for r in rows] == ["https://weidian.com/item.html?itemID=3"]
```

- [ ] **Step 5: Run the full scraper suite**

```bash
TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test .venv/bin/python -m pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scraper
git commit -m "feat: platform-aware scraper db layer, capped weidian-only revalidation"
```

---

### Task 3: Sheet-key extraction + product-link resolution

**Files:**
- Modify: `scraper/scraper/extract.py`
- Test: `scraper/tests/test_extract.py`

**Interfaces:**
- Produces: `extract_sheet_keys(text: str) -> list[str]` (ordered, deduped Google sheet keys); `resolve_product_link(url: str) -> tuple[str, str] | None` returning `(platform, canonical_url)` with platform `'weidian' | 'taobao'`, or None.

- [ ] **Step 1: Write the failing tests** (append to `scraper/tests/test_extract.py`)

```python
def test_extract_sheet_keys():
    from scraper.extract import extract_sheet_keys

    text = (
        "sheet https://docs.google.com/spreadsheets/d/1AbC-dEf_2345678901234567890123456789012/edit#gid=0\n"
        "again https://docs.google.com/spreadsheets/d/1AbC-dEf_2345678901234567890123456789012/htmlview\n"
        "other https://docs.google.com/spreadsheets/d/2XyZ-9876543210987654321098765432109876/edit"
    )
    assert extract_sheet_keys(text) == [
        "1AbC-dEf_2345678901234567890123456789012",
        "2XyZ-9876543210987654321098765432109876",
    ]
    assert extract_sheet_keys("no sheets here") == []


def test_resolve_product_link_direct():
    from scraper.extract import resolve_product_link

    assert resolve_product_link("https://weidian.com/item.html?itemID=123&x=1") == (
        "weidian", "https://weidian.com/item.html?itemID=123")
    assert resolve_product_link("https://item.taobao.com/item.htm?spm=a21n&id=456") == (
        "taobao", "https://item.taobao.com/item.htm?id=456")
    assert resolve_product_link("https://example.com/whatever") is None


def test_resolve_product_link_unwraps_agents():
    from scraper.extract import resolve_product_link

    wrapped = "https://cnfans.com/product/?shop_type=weidian&id=123"
    assert resolve_product_link(wrapped) == ("weidian", "https://weidian.com/item.html?itemID=123")
    assert resolve_product_link("https://www.acbuy.com/product?id=456&source=TB") == (
        "taobao", "https://item.taobao.com/item.htm?id=456")
    url_param = "https://www.superbuy.com/en/page/buy/?url=https%3A%2F%2Fweidian.com%2Fitem.html%3FitemID%3D789"
    assert resolve_product_link(url_param) == ("weidian", "https://weidian.com/item.html?itemID=789")
    nested = "https://mulebuy.com/product/?url=https%3A%2F%2Fitem.taobao.com%2Fitem.htm%3Fid%3D42"
    assert resolve_product_link(nested) == ("taobao", "https://item.taobao.com/item.htm?id=42")
```

- [ ] **Step 2: Run to verify failure**

`.venv/bin/python -m pytest tests/test_extract.py -q` — Expected: FAIL with ImportError.

- [ ] **Step 3: Implement in `scraper/scraper/extract.py`**

```python
from urllib.parse import parse_qs, unquote, urlparse

_SHEET_KEY = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})", re.I)
_TAOBAO_ID = re.compile(r"(?:^|[./])(?:item\.)?taobao\.com/item\.htm\?[^\s\"'<>]*?\bid=(\d+)", re.I)
_AGENT_HOSTS = ("cnfans.com", "acbuy.com", "mulebuy.com", "allchinabuy.com", "superbuy.com", "kakobuy.com")
_AGENT_PLATFORMS = {
    "weidian": "weidian", "wd": "weidian",
    "taobao": "taobao", "tb": "taobao",
}


def extract_sheet_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in _SHEET_KEY.finditer(text or ""):
        if match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def canonical_taobao_url(item_id: str) -> str:
    return f"https://item.taobao.com/item.htm?id={item_id}"


def resolve_product_link(url: str) -> tuple[str, str] | None:
    """Resolve a raw/agent-wrapped link to (platform, canonical product URL)."""
    if not url:
        return None
    weidian_ids = extract_item_ids(url)
    if weidian_ids:
        return ("weidian", canonical_url(weidian_ids[0]))
    taobao = _TAOBAO_ID.search(url)
    if taobao:
        return ("taobao", canonical_taobao_url(taobao.group(1)))

    parsed = urlparse(url if "//" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _AGENT_HOSTS):
        return None
    params = {k.lower(): v[0] for k, v in parse_qs(parsed.query).items() if v}
    if "url" in params:
        return resolve_product_link(unquote(params["url"]))
    item_id = params.get("id")
    platform_raw = params.get("platform") or params.get("source") or params.get("shop_type") or ""
    platform = _AGENT_PLATFORMS.get(platform_raw.lower())
    if item_id and item_id.isdigit() and platform == "weidian":
        return ("weidian", canonical_url(item_id))
    if item_id and item_id.isdigit() and platform == "taobao":
        return ("taobao", canonical_taobao_url(item_id))
    return None
```

- [ ] **Step 4: Run tests** — `.venv/bin/python -m pytest tests/test_extract.py -q` — Expected: PASS (all, including pre-existing).

- [ ] **Step 5: Commit** — `git add scraper && git commit -m "feat: sheet-key extraction and agent-link resolution"`

---

### Task 4: Workbook download, column mapping, tab parsing

**Files:**
- Create: `scraper/scraper/sheets.py`
- Modify: `scraper/requirements.txt` (add `openpyxl==3.1.*`)
- Test: `scraper/tests/test_sheets.py`

**Interfaces:**
- Consumes: `resolve_product_link` from Task 3; `MODEL` from config.
- Produces: `ColumnMap` dataclass (`name_col: int, link_col: int, price_col: int | None, image_col: int | None, currency: str | None`); `map_columns(llm, tab_name: str, preview_rows: list[list]) -> ColumnMap | None`; `parse_tab(ws, colmap: ColumnMap) -> list[dict]` (dict keys: `row_number, name, price_raw, currency, image_url, raw_link, product_url, platform`); `download_workbook(sheet_key: str, client: httpx.Client) -> openpyxl.Workbook`; constants `MAX_TABS = 20`, `MAX_ROWS_PER_TAB = 2000`.

- [ ] **Step 1: Install dep**

Add `openpyxl==3.1.*` to `scraper/requirements.txt`; run `.venv/bin/pip install "openpyxl==3.1.*"`.

- [ ] **Step 2: Write failing tests** (`scraper/tests/test_sheets.py`)

```python
import io
import types

import openpyxl
import pytest

from scraper.sheets import ColumnMap, MAX_ROWS_PER_TAB, map_columns, parse_tab


def make_ws(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    return ws


def test_parse_tab_extracts_rows_and_resolves_links():
    ws = make_ws([
        ["Item", "Price", "Link", "Pic"],
        ["Hellstar hoodie", "¥199", "https://weidian.com/item.html?itemID=11", "https://img/1.jpg"],
        ["AMIRI jeans", "25.5", "https://cnfans.com/product/?shop_type=taobao&id=22", "https://img/2.jpg"],
        ["No link row", "10", "", ""],
    ])
    cm = ColumnMap(name_col=0, price_col=1, link_col=2, image_col=3, currency="USD")
    rows = parse_tab(ws, cm)
    assert rows[0] == {
        "row_number": 2, "name": "Hellstar hoodie", "price_raw": "¥199", "currency": "USD",
        "image_url": "https://img/1.jpg", "raw_link": "https://weidian.com/item.html?itemID=11",
        "product_url": "https://weidian.com/item.html?itemID=11", "platform": "weidian",
    }
    assert rows[1]["platform"] == "taobao"
    assert rows[1]["product_url"] == "https://item.taobao.com/item.htm?id=22"
    assert rows[2]["product_url"] is None
    assert len(rows) == 3  # header skipped, empty name+link rows dropped


def test_parse_tab_uses_hyperlink_target_when_cell_is_display_text():
    ws = make_ws([["Item", "Link"], ["hoodie", "click here"]])
    ws.cell(row=2, column=2).hyperlink = "https://weidian.com/item.html?itemID=99"
    cm = ColumnMap(name_col=0, price_col=None, link_col=1, image_col=None, currency=None)
    rows = parse_tab(ws, cm)
    assert rows[0]["product_url"] == "https://weidian.com/item.html?itemID=99"


def test_parse_tab_caps_rows():
    data = [["Item", "Link"]] + [[f"i{n}", "https://weidian.com/item.html?itemID=1"] for n in range(MAX_ROWS_PER_TAB + 50)]
    ws = make_ws(data)
    cm = ColumnMap(name_col=0, price_col=None, link_col=1, image_col=None, currency=None)
    assert len(parse_tab(ws, cm)) == MAX_ROWS_PER_TAB


class FakeLLM:
    def __init__(self, text):
        self._text = text
        self.messages = self

    def create(self, **kwargs):
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=self._text)])


def test_map_columns_parses_response():
    llm = FakeLLM('{"is_items": true, "name_col": 0, "price_col": 1, "link_col": 2, "image_col": null, "currency": "CNY"}')
    cm = map_columns(llm, "Hoodies", [["Item", "Price", "Link"]])
    assert cm == ColumnMap(name_col=0, price_col=1, link_col=2, image_col=None, currency="CNY")


def test_map_columns_not_items_tab_returns_none():
    llm = FakeLLM('{"is_items": false, "name_col": null, "price_col": null, "link_col": null, "image_col": null, "currency": null}')
    assert map_columns(llm, "Intro", [["Welcome to the sheet"]]) is None


def test_map_columns_requires_name_and_link():
    llm = FakeLLM('{"is_items": true, "name_col": 0, "price_col": null, "link_col": null, "image_col": null, "currency": null}')
    assert map_columns(llm, "Tab", [["Item"]]) is None
```

- [ ] **Step 3: Run to verify failure** — `.venv/bin/python -m pytest tests/test_sheets.py -q` — Expected: ImportError.

- [ ] **Step 4: Implement `scraper/scraper/sheets.py`**

```python
"""Google-Sheets W2C spreadsheet download and parsing."""

import io
import json
import logging
from dataclasses import dataclass

import httpx
import openpyxl

from .config import MODEL, USER_AGENT
from .extract import resolve_product_link

logger = logging.getLogger(__name__)

MAX_TABS = 20
MAX_ROWS_PER_TAB = 2000
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{key}/export?format=xlsx"

COLUMN_MAP_PROMPT = """You are looking at the first rows of one tab of a community fashion-item spreadsheet. Decide whether this tab lists purchasable items, and if so which 0-based column index holds each field.

Respond with ONLY a JSON object, no other text:
{{"is_items": boolean, "name_col": int or null, "price_col": int or null, "link_col": int or null, "image_col": int or null, "currency": "CNY" | "USD" or null}}

`link_col` is the column with purchase links (weidian/taobao/agent links). A tab without both an item-name column and a link column is not an items tab.

TAB NAME: {tab_name}

FIRST ROWS (each line is one row, cells joined by " | "):
{preview}
"""


@dataclass
class ColumnMap:
    name_col: int
    link_col: int
    price_col: int | None
    image_col: int | None
    currency: str | None


def download_workbook(sheet_key: str, client: httpx.Client) -> openpyxl.Workbook:
    resp = client.get(
        EXPORT_URL.format(key=sheet_key),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=60,
    )
    resp.raise_for_status()
    # read_only=False: read-only worksheets don't expose cell.hyperlink,
    # which parse_tab needs for display-text link cells.
    return openpyxl.load_workbook(io.BytesIO(resp.content), read_only=False, data_only=True)


def _extract_text(message) -> str:
    content = getattr(message, "content", None)
    if not content:
        raise ValueError("empty or non-text response")
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        raise ValueError("empty or non-text response")
    return text


def parse_column_map(text: str) -> ColumnMap | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in column-map response")
    data = json.loads(text[start : end + 1])
    if not isinstance(data.get("is_items"), bool):
        raise ValueError("is_items missing")
    if not data["is_items"]:
        return None
    name_col, link_col = data.get("name_col"), data.get("link_col")
    if not isinstance(name_col, int) or not isinstance(link_col, int):
        return None
    currency = data.get("currency")
    return ColumnMap(
        name_col=name_col,
        link_col=link_col,
        price_col=data.get("price_col") if isinstance(data.get("price_col"), int) else None,
        image_col=data.get("image_col") if isinstance(data.get("image_col"), int) else None,
        currency=currency if currency in ("CNY", "USD") else None,
    )


def map_columns(llm, tab_name: str, preview_rows: list[list]) -> ColumnMap | None:
    preview = "\n".join(
        " | ".join("" if c is None else str(c) for c in row) for row in preview_rows[:10]
    )
    prompt = COLUMN_MAP_PROMPT.format(tab_name=tab_name, preview=preview[:4000])
    last_err: Exception | None = None
    for _ in range(2):  # initial attempt + 1 retry
        message = llm.messages.create(
            model=MODEL, max_tokens=256, messages=[{"role": "user", "content": prompt}]
        )
        try:
            return parse_column_map(_extract_text(message))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    logger.warning("column mapping unparseable for tab %s: %s", tab_name, last_err)
    return None


def _cell_link(ws_row, col: int) -> str:
    cell = ws_row[col] if col < len(ws_row) else None
    if cell is None:
        return ""
    link = getattr(cell, "hyperlink", None)
    if link is not None and getattr(link, "target", None):
        return str(link.target)
    return "" if cell.value is None else str(cell.value)


def _cell_text(ws_row, col: int | None) -> str | None:
    if col is None or col >= len(ws_row):
        return None
    value = ws_row[col].value
    return None if value is None else str(value).strip() or None


def parse_tab(ws, colmap: ColumnMap) -> list[dict]:
    rows: list[dict] = []
    for row_number, ws_row in enumerate(ws.iter_rows(), start=1):
        if row_number == 1:
            continue  # header
        if len(rows) >= MAX_ROWS_PER_TAB:
            break
        name = _cell_text(ws_row, colmap.name_col)
        raw_link = _cell_link(ws_row, colmap.link_col).strip()
        if not name and not raw_link:
            continue
        resolved = resolve_product_link(raw_link)
        rows.append({
            "row_number": row_number,
            "name": name,
            "price_raw": _cell_text(ws_row, colmap.price_col),
            "currency": colmap.currency,
            "image_url": _cell_text(ws_row, colmap.image_col),
            "raw_link": raw_link or None,
            "product_url": resolved[1] if resolved else None,
            "platform": resolved[0] if resolved else None,
        })
    return rows
```

- [ ] **Step 5: Run tests** — `.venv/bin/python -m pytest tests/test_sheets.py -q` — Expected: PASS.

- [ ] **Step 6: Commit** — `git add scraper && git commit -m "feat: workbook download, LLM column mapping, tab parsing"`

---

### Task 5: Staging DB layer + sheet sync stage + discovery hook

**Files:**
- Modify: `scraper/scraper/db.py`, `scraper/scraper/sheets.py`, `scraper/scraper/run.py`
- Test: `scraper/tests/test_db.py`, `scraper/tests/test_sheets.py`, `scraper/tests/test_run.py`

**Interfaces:**
- Consumes: Task 4 `download_workbook/map_columns/parse_tab`; Task 3 `extract_sheet_keys`.
- Produces:
  - `db.upsert_spreadsheet(conn, sheet_key: str, url: str, post_row_id: int | None) -> int`
  - `db.sheets_due_for_sync(conn, days: int = 7) -> list[tuple[int, str]]` (`(id, sheet_key)`)
  - `db.mark_sheet_synced(conn, spreadsheet_id: int, title: str | None = None, error: str | None = None) -> None` (repeated errors handled by caller; `status='gone'` set when `error` given and previous `sync_error` was also set)
  - `db.upsert_sheet_rows(conn, spreadsheet_id: int, tab_name: str, rows: list[dict]) -> None` (upsert on `(spreadsheet_id, tab_name, row_number)`; then links rows whose `product_url` already exists in items: sets `item_id` and inserts `item_spreadsheet_mentions`)
  - `sheets.sync_spreadsheets(conn, llm, http_client) -> None`
  - `run.run_pipeline` gains a `deps.sync_sheets: Callable[[], None]` stage executed after ingest, before revalidate; discovery records sheet links via `db.upsert_spreadsheet` for every examined post.

- [ ] **Step 1: Write failing DB tests** (append to `scraper/tests/test_db.py`; follow the existing `conn` fixture style)

```python
def test_upsert_spreadsheet_idempotent(conn):
    a = db.upsert_spreadsheet(conn, "key1", "https://docs.google.com/spreadsheets/d/key1", None)
    b = db.upsert_spreadsheet(conn, "key1", "https://docs.google.com/spreadsheets/d/key1", None)
    assert a == b
    assert conn.execute("SELECT count(*) FROM spreadsheets").fetchone()[0] == 1


def test_upsert_sheet_rows_upserts_and_links_existing_items(conn):
    sid = db.upsert_spreadsheet(conn, "key2", "u", None)
    conn.execute(
        "INSERT INTO items (product_url, platform, status) VALUES"
        " ('https://weidian.com/item.html?itemID=11', 'weidian', 'active')"
    )
    rows = [{
        "row_number": 2, "name": "hoodie", "price_raw": "199", "currency": "CNY",
        "image_url": None, "raw_link": "x", "product_url": "https://weidian.com/item.html?itemID=11",
        "platform": "weidian",
    }]
    db.upsert_sheet_rows(conn, sid, "Hoodies", rows)
    db.upsert_sheet_rows(conn, sid, "Hoodies", rows)  # re-sync: no dup
    assert conn.execute("SELECT count(*) FROM spreadsheet_rows").fetchone()[0] == 1
    linked = conn.execute("SELECT item_id FROM spreadsheet_rows").fetchone()[0]
    assert linked is not None
    assert conn.execute("SELECT count(*) FROM item_spreadsheet_mentions").fetchone()[0] == 1


def test_sheets_due_for_sync(conn):
    fresh = db.upsert_spreadsheet(conn, "k-fresh", "u", None)
    conn.execute("UPDATE spreadsheets SET last_synced_at = now() WHERE id = %s", (fresh,))
    stale = db.upsert_spreadsheet(conn, "k-stale", "u", None)
    conn.execute("UPDATE spreadsheets SET last_synced_at = now() - interval '8 days' WHERE id = %s", (stale,))
    never = db.upsert_spreadsheet(conn, "k-never", "u", None)
    due = {row[0] for row in db.sheets_due_for_sync(conn)}
    assert due == {stale, never}


def test_mark_sheet_synced_gone_after_repeated_error(conn):
    sid = db.upsert_spreadsheet(conn, "k-err", "u", None)
    db.mark_sheet_synced(conn, sid, error="403 Forbidden")
    assert conn.execute("SELECT status FROM spreadsheets WHERE id=%s", (sid,)).fetchone()[0] == "active"
    db.mark_sheet_synced(conn, sid, error="403 Forbidden")
    assert conn.execute("SELECT status FROM spreadsheets WHERE id=%s", (sid,)).fetchone()[0] == "gone"
```

- [ ] **Step 2: Run to verify failure**, then implement in `scraper/scraper/db.py`:

```python
def upsert_spreadsheet(conn: psycopg.Connection, sheet_key: str, url: str, post_row_id: int | None) -> int:
    row = conn.execute(
        """
        INSERT INTO spreadsheets (sheet_key, url, discovered_post_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (sheet_key) DO UPDATE SET sheet_key = EXCLUDED.sheet_key
        RETURNING id
        """,
        (sheet_key, url, post_row_id),
    ).fetchone()
    return row[0]


def sheets_due_for_sync(conn: psycopg.Connection, days: int = 7) -> list[tuple[int, str]]:
    return conn.execute(
        """
        SELECT id, sheet_key FROM spreadsheets
        WHERE status = 'active'
          AND (last_synced_at IS NULL OR last_synced_at < now() - make_interval(days => %s))
        ORDER BY last_synced_at NULLS FIRST, id
        """,
        (days,),
    ).fetchall()


def mark_sheet_synced(conn: psycopg.Connection, spreadsheet_id: int, title: str | None = None, error: str | None = None) -> None:
    if error is None:
        conn.execute(
            "UPDATE spreadsheets SET last_synced_at = now(), sync_error = NULL, title = coalesce(%s, title) WHERE id = %s",
            (title, spreadsheet_id),
        )
    else:
        # second consecutive failure marks the sheet gone
        conn.execute(
            """
            UPDATE spreadsheets
            SET last_synced_at = now(),
                status = CASE WHEN sync_error IS NOT NULL THEN 'gone' ELSE status END,
                sync_error = %s
            WHERE id = %s
            """,
            (error, spreadsheet_id),
        )


def upsert_sheet_rows(conn: psycopg.Connection, spreadsheet_id: int, tab_name: str, rows: list[dict]) -> None:
    for r in rows:
        conn.execute(
            """
            INSERT INTO spreadsheet_rows
              (spreadsheet_id, tab_name, row_number, name, price_raw, currency,
               image_url, raw_link, product_url, platform)
            VALUES (%(sid)s, %(tab)s, %(row_number)s, %(name)s, %(price_raw)s, %(currency)s,
                    %(image_url)s, %(raw_link)s, %(product_url)s, %(platform)s)
            ON CONFLICT (spreadsheet_id, tab_name, row_number) DO UPDATE
              SET name = EXCLUDED.name, price_raw = EXCLUDED.price_raw,
                  currency = EXCLUDED.currency, image_url = EXCLUDED.image_url,
                  raw_link = EXCLUDED.raw_link, product_url = EXCLUDED.product_url,
                  platform = EXCLUDED.platform
            """,
            {**r, "sid": spreadsheet_id, "tab": tab_name},
        )
    conn.execute(
        """
        UPDATE spreadsheet_rows sr SET item_id = i.id
        FROM items i
        WHERE sr.spreadsheet_id = %s AND sr.item_id IS NULL AND sr.product_url = i.product_url
        """,
        (spreadsheet_id,),
    )
    conn.execute(
        """
        INSERT INTO item_spreadsheet_mentions (item_id, spreadsheet_id)
        SELECT DISTINCT sr.item_id, sr.spreadsheet_id FROM spreadsheet_rows sr
        WHERE sr.spreadsheet_id = %s AND sr.item_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
        (spreadsheet_id,),
    )
```

Run the new tests: PASS. Commit: `git commit -am "feat: spreadsheet staging db layer"`.

- [ ] **Step 3: Write failing sync-orchestration test** (append to `scraper/tests/test_sheets.py`)

```python
from tests.conftest import requires_db


@requires_db
def test_sync_spreadsheets_stages_rows(conn):
    import httpx

    from scraper import db
    from scraper.sheets import sync_spreadsheets

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoodies"
    ws.append(["Item", "Price", "Link"])
    ws.append(["Hellstar hoodie", "199", "https://weidian.com/item.html?itemID=77"])
    buf = io.BytesIO()
    wb.save(buf)

    def handler(request):
        return httpx.Response(200, content=buf.getvalue())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = FakeLLM('{"is_items": true, "name_col": 0, "price_col": 1, "link_col": 2, "image_col": null, "currency": "CNY"}')

    db.upsert_spreadsheet(conn, "sync-key", "https://docs.google.com/spreadsheets/d/sync-key", None)
    sync_spreadsheets(conn, llm, client)

    row = conn.execute("SELECT name, product_url, platform FROM spreadsheet_rows").fetchone()
    assert row == ("Hellstar hoodie", "https://weidian.com/item.html?itemID=77", "weidian")
    assert conn.execute("SELECT last_synced_at FROM spreadsheets").fetchone()[0] is not None


@requires_db
def test_sync_spreadsheets_records_error(conn):
    import httpx

    from scraper import db
    from scraper.sheets import sync_spreadsheets

    def handler(request):
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db.upsert_spreadsheet(conn, "denied-key", "u", None)
    sync_spreadsheets(conn, None, client)  # llm never reached
    err = conn.execute("SELECT sync_error FROM spreadsheets").fetchone()[0]
    assert err and "403" in err
```

(`conn` fixture comes from conftest; add `from tests.conftest import requires_db` and mark only these two tests — the module's other tests stay DB-free.)

- [ ] **Step 4: Implement `sync_spreadsheets` in `scraper/scraper/sheets.py`**

```python
from . import db


def sync_sheet(conn, llm, http_client, spreadsheet_id: int, sheet_key: str) -> None:
    workbook = download_workbook(sheet_key, http_client)
    title = None
    for ws in workbook.worksheets[:MAX_TABS]:
        preview = [[c.value for c in row] for row in ws.iter_rows(max_row=10)]
        colmap = map_columns(llm, ws.title, preview)
        if colmap is None:
            continue
        title = title or workbook.properties.title or ws.title
        db.upsert_sheet_rows(conn, spreadsheet_id, ws.title, parse_tab(ws, colmap))
    db.mark_sheet_synced(conn, spreadsheet_id, title=title)


def sync_spreadsheets(conn, llm, http_client) -> None:
    for spreadsheet_id, sheet_key in db.sheets_due_for_sync(conn):
        try:
            sync_sheet(conn, llm, http_client, spreadsheet_id, sheet_key)
        except Exception as e:
            logger.warning("sheet sync failed for %s", sheet_key, exc_info=True)
            db.mark_sheet_synced(conn, spreadsheet_id, error=f"{type(e).__name__}: {e}")
```

Run: PASS. Commit: `git commit -am "feat: spreadsheet sync stage"`.

- [ ] **Step 5: Wire discovery + the stage into the pipeline** (failing test first, append to `scraper/tests/test_run.py`)

```python
def test_sheet_links_recorded_and_sync_stage_runs(conn):
    posts = [make_post("p20", "check https://docs.google.com/spreadsheets/d/1SheetKeyAbcdefghijklmnop123456789/edit")]
    deps = make_deps(posts, JudgeResult(True, [], None, None, None, ""))
    called = []
    deps.sync_sheets = lambda: called.append(True)
    run_pipeline(conn, deps)
    assert conn.execute("SELECT sheet_key FROM spreadsheets").fetchone()[0] == "1SheetKeyAbcdefghijklmnop123456789"
    assert called == [True]
```

In `run.py`: add `sync_sheets: Callable[[], None]` to `Deps` (and `sync_sheets=lambda: None` to `make_deps` in tests). In the post loop, right after `url_contexts = extract_urls_with_context(chunks)` add:

```python
                for key in extract_sheet_keys("\n".join(chunks)):
                    db.upsert_spreadsheet(
                        conn, key, f"https://docs.google.com/spreadsheets/d/{key}", None
                    )
```

(import `extract_sheet_keys` next to `extract_urls_with_context`). After the post loop, before `stats.items_deactivated = deps.revalidate(conn)`:

```python
        deps.sync_sheets()
```

`build_default_deps` currently takes no arguments; change its signature to `def build_default_deps(conn) -> Deps:` and update `main()` to create `conn` first and pass it in. Then:

```python
    import httpx as _httpx

    from . import sheets

    sheet_client = _httpx.Client()
    ...
        sync_sheets=lambda: sheets.sync_spreadsheets(conn, llm, sheet_client),
```

- [ ] **Step 6: Run the whole scraper suite** — Expected: PASS. Commit: `git commit -am "feat: sheet discovery in pipeline + sync stage"`.

---

### Task 6: Promotion stage

**Files:**
- Create: `scraper/scraper/promote.py`
- Modify: `scraper/scraper/db.py`, `scraper/scraper/run.py`
- Test: `scraper/tests/test_promote.py`

**Interfaces:**
- Consumes: `db.upsert_item`, `weidian.fetch_rendered/detect_liveness/parse_listing_html`, `translate_listing`, `config.USD_TO_CNY`.
- Produces:
  - `db.rows_to_promote(conn, budget: int, requested_only: bool = False) -> list[dict]` (keys: `id, spreadsheet_id, name, price_raw, currency, image_url, product_url, platform`; only `item_id IS NULL AND promote_error IS NULL AND product_url IS NOT NULL`; requested rows first by `requested_at` asc, then `created_at` desc)
  - `db.mark_row_promoted(conn, row_id: int, item_id: int) -> None` (also inserts `item_spreadsheet_mentions`)
  - `db.mark_row_error(conn, row_id: int, error: str) -> None`
  - `db.upsert_sheet_item(conn, row: dict, translation) -> int` (taobao path: `platform` from row, `price_cny` computed by caller and passed inside `row["price_cny"]`)
  - `promote.promote_rows(conn, fetch_page, translate, budget: int = 200, requested_only: bool = False) -> int` (returns promoted count)
  - `run_pipeline` calls the promotion stage via `deps.promote: Callable[[], int]` after `sync_sheets`.

- [ ] **Step 1: Failing tests** (`scraper/tests/test_promote.py`)

```python
from tests.conftest import requires_db

from scraper import db
from scraper.models import Translation
from scraper.promote import promote_rows, sheet_price_cny

pytestmark = requires_db

LIVE_HTML = (
    '<html><head><meta property="og:title" content="帽衫"/>'
    '<meta property="og:image" content="https://si.geilicdn.com/a.jpg"/></head><body></body></html>'
)


def stage_row(conn, n, product_url, platform, requested=False, name="hoodie"):
    sid = db.upsert_spreadsheet(conn, f"k{n}", "u", None)
    db.upsert_sheet_rows(conn, sid, "Tab", [{
        "row_number": n, "name": name, "price_raw": "199", "currency": "CNY",
        "image_url": "https://img/x.jpg", "raw_link": product_url,
        "product_url": product_url, "platform": platform,
    }])
    if requested:
        conn.execute("UPDATE spreadsheet_rows SET requested_at = now()")
    return sid


def test_sheet_price_cny():
    assert sheet_price_cny("¥199", "CNY") == 199.0
    assert sheet_price_cny("25.5", "USD") == round(25.5 * 7.14, 2)
    assert sheet_price_cny("25.5", None) is None
    assert sheet_price_cny(None, "CNY") is None
    assert sheet_price_cny("ask seller", "CNY") is None


def test_promote_weidian_row_uses_live_fetch(conn):
    stage_row(conn, 2, "https://weidian.com/item.html?itemID=501", "weidian")
    count = promote_rows(
        conn,
        fetch_page=lambda url: (LIVE_HTML, 200),
        translate=lambda listing, context: Translation("CH hoodie", "d", brand="Chrome Hearts", category="clothing"),
    )
    assert count == 1
    item = conn.execute("SELECT platform, title_en, brand FROM items").fetchone()
    assert item == ("weidian", "CH hoodie", "Chrome Hearts")
    assert conn.execute("SELECT item_id FROM spreadsheet_rows").fetchone()[0] is not None
    assert conn.execute("SELECT count(*) FROM item_spreadsheet_mentions").fetchone()[0] == 1


def test_promote_taobao_row_from_sheet_data(conn):
    stage_row(conn, 3, "https://item.taobao.com/item.htm?id=88", "taobao", name="AMIRI jeans")
    count = promote_rows(
        conn,
        fetch_page=lambda url: (_ for _ in ()).throw(AssertionError("taobao must not be fetched")),
        translate=lambda listing, context: Translation("AMIRI jeans", "", brand="AMIRI", category="clothing"),
    )
    assert count == 1
    item = conn.execute(
        "SELECT platform, title_en, brand, price_cny::float, image_urls FROM items"
    ).fetchone()
    assert item[0] == "taobao"
    assert item[1] == "AMIRI jeans"
    assert item[2] == "AMIRI"
    assert item[3] == 199.0
    assert item[4] == ["https://img/x.jpg"]


def test_promote_requested_rows_first_and_budget(conn):
    stage_row(conn, 4, "https://weidian.com/item.html?itemID=601", "weidian")
    stage_row(conn, 5, "https://weidian.com/item.html?itemID=602", "weidian", requested=True)
    count = promote_rows(
        conn,
        fetch_page=lambda url: (LIVE_HTML, 200),
        translate=lambda listing, context: Translation("x", "d"),
        budget=1,
    )
    assert count == 1
    promoted = conn.execute(
        "SELECT product_url FROM spreadsheet_rows WHERE item_id IS NOT NULL"
    ).fetchall()
    assert promoted == [("https://weidian.com/item.html?itemID=602",)]


def test_promote_failure_records_error_and_continues(conn):
    stage_row(conn, 6, "https://weidian.com/item.html?itemID=701", "weidian")
    stage_row(conn, 7, "https://weidian.com/item.html?itemID=702", "weidian")

    def flaky(url):
        if "701" in url:
            raise TimeoutError("down")
        return LIVE_HTML, 200

    count = promote_rows(conn, fetch_page=flaky, translate=lambda l, c: Translation("x", "d"))
    assert count == 1
    assert conn.execute(
        "SELECT count(*) FROM spreadsheet_rows WHERE promote_error IS NOT NULL"
    ).fetchone()[0] == 1
```

- [ ] **Step 2: Run to verify failure**, then implement.

`scraper/scraper/db.py` additions:

```python
def rows_to_promote(conn: psycopg.Connection, budget: int, requested_only: bool = False) -> list[dict]:
    where_requested = "AND requested_at IS NOT NULL" if requested_only else ""
    rows = conn.execute(
        f"""
        SELECT id, spreadsheet_id, name, price_raw, currency, image_url, product_url, platform
        FROM spreadsheet_rows
        WHERE item_id IS NULL AND promote_error IS NULL AND product_url IS NOT NULL
          {where_requested}
        ORDER BY (requested_at IS NULL), requested_at, created_at DESC, id
        LIMIT %s
        """,
        (budget,),
    ).fetchall()
    cols = ["id", "spreadsheet_id", "name", "price_raw", "currency", "image_url", "product_url", "platform"]
    return [dict(zip(cols, r)) for r in rows]


def mark_row_promoted(conn: psycopg.Connection, row_id: int, item_id: int) -> None:
    conn.execute("UPDATE spreadsheet_rows SET item_id = %s WHERE id = %s", (item_id, row_id))
    conn.execute(
        """
        INSERT INTO item_spreadsheet_mentions (item_id, spreadsheet_id)
        SELECT %s, spreadsheet_id FROM spreadsheet_rows WHERE id = %s
        ON CONFLICT DO NOTHING
        """,
        (item_id, row_id),
    )


def mark_row_error(conn: psycopg.Connection, row_id: int, error: str) -> None:
    conn.execute("UPDATE spreadsheet_rows SET promote_error = %s WHERE id = %s", (error, row_id))


def upsert_sheet_item(conn: psycopg.Connection, row: dict, translation: Translation) -> int:
    out = conn.execute(
        """
        INSERT INTO items
          (product_url, platform_item_id, platform, title_en, description_en,
           brand, category, price_cny, image_urls, status, last_validated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', NULL)
        ON CONFLICT (product_url) DO UPDATE
          SET title_en = EXCLUDED.title_en,
              brand = EXCLUDED.brand,
              category = EXCLUDED.category,
              price_cny = EXCLUDED.price_cny,
              image_urls = EXCLUDED.image_urls,
              updated_at = now()
        RETURNING id
        """,
        (
            row["product_url"],
            row["product_url"].rsplit("=", 1)[-1],
            row["platform"],
            translation.title_en,
            translation.description_en,
            translation.brand,
            translation.category,
            row.get("price_cny"),
            json.dumps([row["image_url"]] if row.get("image_url") else []),
        ),
    ).fetchone()
    return out[0]
```

`scraper/scraper/promote.py`:

```python
"""Budgeted promotion of staged spreadsheet rows into the items catalog."""

import logging
import re

from . import db
from .config import USD_TO_CNY
from .models import JudgeResult, WeidianListing
from .weidian import Liveness, detect_liveness, parse_listing_html

logger = logging.getLogger(__name__)

# Sheet rows bypass the sentiment judge: the sheet's curation is the signal.
NEUTRAL_JUDGE = JudgeResult(
    positive_sentiment=True, red_flags=[], brand=None, category=None,
    item_name=None, quality_summary="",
)

_NUM = re.compile(r"\d+(?:\.\d+)?")


def sheet_price_cny(price_raw: str | None, currency: str | None) -> float | None:
    if not price_raw or currency not in ("CNY", "USD"):
        return None
    match = _NUM.search(price_raw)
    if not match:
        return None
    value = float(match.group(0))
    return value if currency == "CNY" else round(value * USD_TO_CNY, 2)


def _promote_weidian(conn, row: dict, fetch_page, translate) -> int | None:
    html, status = fetch_page(row["product_url"])
    if detect_liveness(html, status) is not Liveness.LIVE:
        db.mark_row_error(conn, row["id"], "not live at promotion")
        return None
    listing = parse_listing_html(html, row["product_url"])
    translation = translate(listing, row.get("name") or "")
    return db.upsert_item(conn, listing, translation, NEUTRAL_JUDGE)


def _promote_taobao(conn, row: dict, translate) -> int:
    # No taobao page scraping (login-walled): the sheet's own data is the listing.
    listing = WeidianListing(
        weidian_url=row["product_url"], weidian_item_id=None,
        title_zh=row.get("name") or "", description_zh="",
        price_cny=None, seller_name=None, image_urls=[],
    )
    translation = translate(listing, row.get("name") or "")
    return db.upsert_sheet_item(
        conn, {**row, "price_cny": sheet_price_cny(row.get("price_raw"), row.get("currency"))}, translation
    )


def promote_rows(conn, fetch_page, translate, budget: int = 200, requested_only: bool = False) -> int:
    promoted = 0
    for row in db.rows_to_promote(conn, budget, requested_only=requested_only):
        try:
            if row["platform"] == "weidian":
                item_id = _promote_weidian(conn, row, fetch_page, translate)
            else:
                item_id = _promote_taobao(conn, row, translate)
            if item_id is not None:
                db.mark_row_promoted(conn, row["id"], item_id)
                promoted += 1
        except Exception as e:
            logger.warning("promotion failed for row %s", row["id"], exc_info=True)
            db.mark_row_error(conn, row["id"], f"{type(e).__name__}: {e}")
    return promoted
```

- [ ] **Step 3: Wire into the pipeline.** Add `promote: Callable[[], int]` to `Deps` (tests' `make_deps` gets `promote=lambda: 0`), call after `deps.sync_sheets()`:

```python
        deps.sync_sheets()
        deps.promote()
```

In `build_default_deps(conn)`:

```python
        promote=lambda: promote_mod.promote_rows(
            conn, fetch_page=fetch_rendered,
            translate=lambda listing, context: translate_mod.translate_listing(llm, listing, context),
        ),
```

- [ ] **Step 4: Run the whole suite** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: budgeted promotion of spreadsheet rows"`

---

### Task 7: Worker entrypoint + deployment

**Files:**
- Create: `scraper/scraper/worker.py`
- Modify: `scraper/Dockerfile`, `README.md`
- Test: `scraper/tests/test_worker.py`

**Interfaces:**
- Consumes: `run_pipeline`, `build_default_deps`, `promote.promote_rows`, `db.get_conn`.
- Produces: `python -m scraper.worker` long-running entrypoint; `worker.daily_run_done(conn) -> bool`; `worker.tick(conn, deps, now) -> None` (pure-ish, testable single iteration).

- [ ] **Step 1: Failing tests** (`scraper/tests/test_worker.py`)

```python
from datetime import datetime, timezone

from scraper.models import JudgeResult
from scraper.worker import DAILY_HOUR_UTC, daily_run_done, tick
from tests.conftest import requires_db
from tests.test_run import make_deps

pytestmark = requires_db


def test_daily_run_done_false_when_no_runs(conn):
    assert daily_run_done(conn) is False


def test_daily_run_done_true_after_todays_run(conn):
    conn.execute("INSERT INTO scrape_runs (started_at, finished_at) VALUES (now(), now())")
    assert daily_run_done(conn) is True


def test_tick_runs_pipeline_once_at_daily_hour(conn):
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    at_nine = datetime(2026, 7, 15, DAILY_HOUR_UTC, 30, tzinfo=timezone.utc)
    tick(conn, deps, now=at_nine)
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 1
    tick(conn, deps, now=at_nine)  # same day: guarded
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 1


def test_tick_before_daily_hour_only_promotes_requested(conn):
    calls = []
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    deps.promote_requested = lambda: calls.append(True) or 0
    early = datetime(2026, 7, 15, DAILY_HOUR_UTC - 1, 0, tzinfo=timezone.utc)
    tick(conn, deps, now=early)
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 0
    assert calls == [True]
```

(Add `promote_requested: Callable[[], int]` to `Deps` with test default `lambda: 0` in `make_deps`.)

- [ ] **Step 2: Implement `scraper/scraper/worker.py`**

```python
"""Always-on worker: 10s promotion polling + internal daily pipeline schedule."""

import logging
import os
import time
from datetime import datetime, timezone

from . import db
from .run import build_default_deps, load_env_file, run_pipeline

logger = logging.getLogger(__name__)

DAILY_HOUR_UTC = 9
POLL_SECONDS = 10
REQUEST_BATCH = 10


def daily_run_done(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM scrape_runs WHERE started_at >= date_trunc('day', now()) LIMIT 1"
    ).fetchone()
    return row is not None


def tick(conn, deps, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if now.hour >= DAILY_HOUR_UTC and not daily_run_done(conn):
        logger.info("worker: starting daily pipeline run")
        try:
            run_pipeline(conn, deps)
        except Exception:
            logger.error("daily run failed", exc_info=True)  # recorded in scrape_runs; guard holds for today
    else:
        deps.promote_requested()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    conn = db.get_conn(os.environ["DATABASE_URL"])
    deps = build_default_deps(conn)
    logger.info("worker started: daily run at %02d:00 UTC, %ss promotion polling", DAILY_HOUR_UTC, POLL_SECONDS)
    while True:
        try:
            tick(conn, deps)
        except Exception:
            logger.error("worker tick failed", exc_info=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
```

In `build_default_deps(conn)` add:

```python
        promote_requested=lambda: promote_mod.promote_rows(
            conn, fetch_page=fetch_rendered,
            translate=lambda listing, context: translate_mod.translate_listing(llm, listing, context),
            budget=10, requested_only=True,
        ),
```

- [ ] **Step 3: Dockerfile + README.** `scraper/Dockerfile` CMD → `CMD ["python", "-m", "scraper.worker"]`. README Railway section: scraper service — remove "Cron Schedule" line, replace with "always-on worker (no cron schedule); Restart policy: Always. Daily scrape runs internally at 09:00 UTC; search-triggered promotions are picked up within ~10s."

- [ ] **Step 4: Run suite** — PASS. **Step 5: Commit** — `git commit -am "feat: always-on worker with daily schedule and promotion polling"`

---

### Task 8: Web search queries + promotion flagging

**Files:**
- Modify: `web/src/db/queries.ts`
- Test: `web/tests/queries.test.ts`

**Interfaces:**
- Consumes: Task 1 schema exports.
- Produces:
  - `searchItems(q: string, opts: { category?: string; brand?: string }) -> Promise<ItemCardData[]>`
  - `type StagingCardData = { id: number; name: string | null; priceRaw: string | null; currency: string | null; imageUrl: string | null; productUrl: string; platform: string; sheetTitle: string | null }`
  - `searchStagingRows(q: string) -> Promise<StagingCardData[]>` (unpromoted rows with a product_url, limit 12)
  - `flagRowsForPromotion(q: string) -> Promise<void>` (sets `requested_at = now()` on top 5 fuzzy-matching unpromoted rows where it's NULL)

- [ ] **Step 1: Failing tests** (append inside the `describe.skipIf(!hasDb)("queries")` block; add staging fixtures to `beforeEach` deletes: `await db.delete(schema.itemSpreadsheetMentions); await db.delete(schema.spreadsheetRows); await db.delete(schema.spreadsheets);` FIRST — FK order)

```ts
  it("searchItems fuzzy-matches title and brand", async () => {
    const hits = await queries.searchItems("hoddie", {});
    expect(hits.map((h) => h.titleEn)).toContain("hot hoodie");
    const brandHits = await queries.searchItems("CH", {});
    expect(brandHits.length).toBeGreaterThan(0);
  });

  it("searchStagingRows matches unpromoted rows and flags top matches", async () => {
    const [sheet] = await db
      .insert(schema.spreadsheets)
      .values({ sheetKey: "sk1", url: "u", title: "Big W2C" })
      .returning();
    await db.insert(schema.spreadsheetRows).values([
      { spreadsheetId: sheet.id, tabName: "T", rowNumber: 2, name: "Hellstar hoodie", productUrl: "https://weidian.com/item.html?itemID=9", platform: "weidian" },
      { spreadsheetId: sheet.id, tabName: "T", rowNumber: 3, name: "unrelated socks", productUrl: "https://weidian.com/item.html?itemID=10", platform: "weidian" },
    ]);
    const rows = await queries.searchStagingRows("hellstar hoodie");
    expect(rows[0].name).toBe("Hellstar hoodie");
    expect(rows[0].sheetTitle).toBe("Big W2C");

    await queries.flagRowsForPromotion("hellstar hoodie");
    const flagged = await db
      .select({ name: schema.spreadsheetRows.name })
      .from(schema.spreadsheetRows)
      .where(sql`requested_at IS NOT NULL`);
    expect(flagged.map((f) => f.name)).toContain("Hellstar hoodie");
  });
```

(import `sql` from drizzle-orm in the test file.)

- [ ] **Step 2: Run to verify failure**, then implement in `web/src/db/queries.ts`:

```ts
const fuzzy = (col: unknown, q: string) =>
  sql`(${col} % ${q} OR ${col} ILIKE ${"%" + q + "%"})`;

export async function searchItems(
  q: string,
  opts: { category?: string; brand?: string },
): Promise<ItemCardData[]> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));
  filters.push(
    sql`(${fuzzy(items.titleEn, q)} OR ${fuzzy(items.brand, q)} OR ${items.titleZh} ILIKE ${"%" + q + "%"})`,
  );
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
    .orderBy(sql`greatest(similarity(coalesce(${items.titleEn}, ''), ${q}), similarity(coalesce(${items.brand}, ''), ${q})) DESC`);
}

export type StagingCardData = {
  id: number;
  name: string | null;
  priceRaw: string | null;
  currency: string | null;
  imageUrl: string | null;
  productUrl: string;
  platform: string;
  sheetTitle: string | null;
};

export async function searchStagingRows(q: string): Promise<StagingCardData[]> {
  const rows = await db
    .select({
      id: spreadsheetRows.id,
      name: spreadsheetRows.name,
      priceRaw: spreadsheetRows.priceRaw,
      currency: spreadsheetRows.currency,
      imageUrl: spreadsheetRows.imageUrl,
      productUrl: spreadsheetRows.productUrl,
      platform: spreadsheetRows.platform,
      sheetTitle: spreadsheets.title,
    })
    .from(spreadsheetRows)
    .innerJoin(spreadsheets, eq(spreadsheets.id, spreadsheetRows.spreadsheetId))
    .where(
      and(
        sql`${spreadsheetRows.itemId} IS NULL`,
        isNotNull(spreadsheetRows.productUrl),
        fuzzy(spreadsheetRows.name, q),
      ),
    )
    .orderBy(sql`similarity(coalesce(${spreadsheetRows.name}, ''), ${q}) DESC`)
    .limit(12);
  return rows as StagingCardData[];
}

export async function flagRowsForPromotion(q: string): Promise<void> {
  await db.execute(sql`
    UPDATE spreadsheet_rows SET requested_at = now()
    WHERE id IN (
      SELECT id FROM spreadsheet_rows
      WHERE item_id IS NULL AND promote_error IS NULL AND product_url IS NOT NULL
        AND requested_at IS NULL
        AND (name % ${q} OR name ILIKE ${"%" + q + "%"})
      ORDER BY similarity(coalesce(name, ''), ${q}) DESC
      LIMIT 5
    )
  `);
}
```

(import `spreadsheets`, `spreadsheetRows` from schema.)

- [ ] **Step 3: Run web tests** — `TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/repnice_test npx vitest run` — Expected: PASS.
- [ ] **Step 4: Commit** — `git commit -am "feat: fuzzy search queries over items and staged spreadsheet rows"`

---

### Task 9: Search UI

**Files:**
- Modify: `web/src/components/FilterBar.tsx`, `web/src/app/page.tsx`
- Create: `web/src/components/StagingCard.tsx`

**Interfaces:**
- Consumes: Task 8 `searchItems/searchStagingRows/flagRowsForPromotion/StagingCardData`; Task 1 `superbuyUrl(productUrl, platform)`.

- [ ] **Step 1: FilterBar search input.** Read `web/src/components/FilterBar.tsx` first and follow its existing pattern (it navigates via URL params). Add a search form that submits `q` while preserving current params:

```tsx
      <form action="" method="get" className="flex gap-2">
        {current.category && <input type="hidden" name="category" value={current.category} />}
        {current.brand && <input type="hidden" name="brand" value={current.brand} />}
        {current.sort && <input type="hidden" name="sort" value={current.sort} />}
        <input
          type="search"
          name="q"
          defaultValue={current.q ?? ""}
          placeholder="Search items… (e.g. hellstar hoodie)"
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm w-56"
        />
        <button type="submit" className="rounded bg-zinc-900 text-white px-3 py-1.5 text-sm">
          Search
        </button>
      </form>
```

(extend the component's `current` prop type with `q?: string`.)

- [ ] **Step 2: `web/src/components/StagingCard.tsx`**

```tsx
import { superbuyUrl } from "@/lib/superbuy";
import type { StagingCardData } from "@/db/queries";
import { ItemImage } from "@/components/ItemImage";
import { cnyToUsd } from "@/lib/format";

export function StagingCard({ row }: { row: StagingCardData }) {
  const price =
    row.priceRaw && row.currency === "CNY"
      ? `¥${row.priceRaw} · ~$${cnyToUsd(Number(row.priceRaw.replace(/[^\d.]/g, "")) || 0).toFixed(0)}`
      : row.priceRaw && row.currency === "USD"
        ? `$${row.priceRaw}`
        : null;
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 p-3 space-y-2">
      <ItemImage src={row.imageUrl ?? undefined} alt={row.name ?? "spreadsheet item"} />
      <h3 className="text-sm font-medium line-clamp-2">{row.name ?? "Untitled"}</h3>
      {price && <p className="text-sm text-zinc-600">{price}</p>}
      <p className="text-xs text-zinc-400">from {row.sheetTitle ?? "a community spreadsheet"} · full details loading…</p>
      <a
        href={superbuyUrl(row.productUrl, row.platform)}
        target="_blank"
        rel="noreferrer"
        className="block text-center rounded bg-zinc-900 text-white text-sm py-1.5"
      >
        Buy via Superbuy
      </a>
    </div>
  );
}
```

(Check `ItemImage`'s actual props first and match them — if it requires different props, adapt this usage, not ItemImage.)

- [ ] **Step 3: `web/src/app/page.tsx`** — extend `SearchParams` with `q?: string`; when `q` is present use search queries and fire the flag update without awaiting completion failure:

```tsx
  const q = params.q?.trim();
  const [itemList, filterOptions, stagingRows] = await Promise.all([
    q ? searchItems(q, { category: params.category, brand: params.brand }) : getItems({ category: params.category, brand: params.brand, sort }),
    getFilterOptions(),
    q ? searchStagingRows(q) : Promise.resolve([]),
  ]);
  if (q) void flagRowsForPromotion(q).catch(() => {});
```

Render a "From community spreadsheets" section under the items grid when `stagingRows.length > 0`:

```tsx
      {stagingRows.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">From community spreadsheets</h2>
          <p className="text-xs text-zinc-500">These match your search but aren&apos;t fully cataloged yet — they&apos;re being fetched now and appear above on your next search.</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {stagingRows.map((row) => (
              <StagingCard key={row.id} row={row} />
            ))}
          </div>
        </section>
      )}
```

Pass `q: params.q` into FilterBar's `current`.

- [ ] **Step 4: Verify end-to-end.**

```bash
cd web && npx vitest run     # all green
DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npm run dev &
# seed one staging row against the catalog DB, then:
curl -s "http://localhost:3000/?q=hoodie" | grep -c "From community spreadsheets"
kill %1
```

Expected: search page renders; with a staged row present, the section appears and its `requested_at` gets set (check via psql).

- [ ] **Step 5: Commit** — `git commit -am "feat: product search UI with spreadsheet staging results"`
