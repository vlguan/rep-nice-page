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
          (product_url, platform_item_id, platform, title_zh, title_en, description_en,
           brand, category, price_cny, seller_name, seller_rebuy_rate, image_urls,
           status, last_validated_at)
        VALUES (%s, %s, 'weidian', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', now())
        ON CONFLICT (product_url) DO UPDATE
          SET status = 'active',
              dead_since = NULL,
              title_zh = EXCLUDED.title_zh,
              title_en = EXCLUDED.title_en,
              description_en = EXCLUDED.description_en,
              brand = EXCLUDED.brand,
              category = EXCLUDED.category,
              price_cny = EXCLUDED.price_cny,
              seller_rebuy_rate = EXCLUDED.seller_rebuy_rate,
              image_urls = EXCLUDED.image_urls,
              last_validated_at = now(),
              updated_at = now()
        RETURNING id
        """,
        (
            listing.weidian_url, listing.weidian_item_id, listing.title_zh,
            translation.title_en, translation.description_en,
            # per-item classification from translation wins over the
            # judge's single post-level guess (wrong for multi-item hauls)
            translation.brand or judge.brand,
            translation.category or judge.category,
            listing.price_cny,
            listing.seller_name, listing.seller_rebuy_rate, json.dumps(listing.image_urls),
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
