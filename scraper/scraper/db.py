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
