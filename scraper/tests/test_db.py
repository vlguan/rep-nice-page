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

    row = conn.execute(
        "SELECT id, product_url, status FROM items WHERE id = %s", (item_id,)
    ).fetchone()
    assert row == (item_id, LISTING.weidian_url, "active")


def test_get_items_for_validation_skips_taobao_and_fresh(conn):
    from scraper import db

    conn.execute(
        "INSERT INTO items (product_url, platform, status, last_validated_at) VALUES"
        " ('https://item.taobao.com/item.htm?id=1', 'taobao', 'active', NULL),"
        " ('https://weidian.com/item.html?itemID=2', 'weidian', 'active', now()),"
        " ('https://weidian.com/item.html?itemID=3', 'weidian', 'active', now() - interval '8 days')"
    )
    rows = db.get_items_for_validation(conn)
    assert [r[1] for r in rows] == ["https://weidian.com/item.html?itemID=3"]


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
