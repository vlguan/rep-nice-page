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


def test_link_mention_stores_quote_and_keeps_it_on_relink(conn):
    from scraper import db

    post_id = db.insert_post(conn, POST, "positive", None)
    item_id = db.upsert_item(conn, LISTING, TRANSLATION, JUDGE)
    db.link_mention(conn, item_id, post_id, quote="fits TTS, 8/10")
    db.link_mention(conn, item_id, post_id)  # re-link without quote must not wipe it

    quote = conn.execute(
        "SELECT quote FROM item_mentions WHERE item_id = %s AND reddit_post_id = %s",
        (item_id, post_id),
    ).fetchone()[0]
    assert quote == "fits TTS, 8/10"


def test_dedupe_shared_images_strips_chrome_keeps_unique(conn):
    import json as _json

    from scraper import db

    def mk(url_id, imgs):
        listing = WeidianListing(
            weidian_url=f"https://weidian.com/item.html?itemID={url_id}",
            weidian_item_id=str(url_id), title_zh="x", description_zh="",
            price_cny=1.0, seller_name=None, image_urls=imgs,
        )
        return db.upsert_item(conn, listing, TRANSLATION, JUDGE)

    chrome = "https://si.geilicdn.com/hz_img_logo.png"  # appears on every item
    a = mk(1, ["https://si.geilicdn.com/prodA.jpg", chrome])
    b = mk(2, ["https://si.geilicdn.com/prodB.jpg", chrome])
    c = mk(3, [chrome])  # only chrome -> becomes empty

    changed = db.dedupe_shared_images(conn)
    assert changed == 3
    galleries = {
        r[0]: r[1]
        for r in conn.execute("SELECT id, image_urls FROM items WHERE id = ANY(%s)", ([a, b, c],)).fetchall()
    }
    assert galleries[a] == ["https://si.geilicdn.com/prodA.jpg"]
    assert galleries[b] == ["https://si.geilicdn.com/prodB.jpg"]
    assert galleries[c] == []


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


def test_upsert_spreadsheet_idempotent(conn):
    from scraper import db

    a = db.upsert_spreadsheet(conn, "key1", "https://docs.google.com/spreadsheets/d/key1", None)
    b = db.upsert_spreadsheet(conn, "key1", "https://docs.google.com/spreadsheets/d/key1", None)
    assert a == b
    assert conn.execute("SELECT count(*) FROM spreadsheets").fetchone()[0] == 1


def test_upsert_sheet_rows_upserts_and_links_existing_items(conn):
    from scraper import db

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
    from scraper import db

    fresh = db.upsert_spreadsheet(conn, "k-fresh", "u", None)
    conn.execute("UPDATE spreadsheets SET last_synced_at = now() WHERE id = %s", (fresh,))
    stale = db.upsert_spreadsheet(conn, "k-stale", "u", None)
    conn.execute("UPDATE spreadsheets SET last_synced_at = now() - interval '8 days' WHERE id = %s", (stale,))
    never = db.upsert_spreadsheet(conn, "k-never", "u", None)
    due = {row[0] for row in db.sheets_due_for_sync(conn)}
    assert due == {stale, never}


def test_mark_sheet_synced_gone_after_repeated_error(conn):
    from scraper import db

    sid = db.upsert_spreadsheet(conn, "k-err", "u", None)
    db.mark_sheet_synced(conn, sid, error="403 Forbidden")
    assert conn.execute("SELECT status FROM spreadsheets WHERE id=%s", (sid,)).fetchone()[0] == "active"
    db.mark_sheet_synced(conn, sid, error="403 Forbidden")
    assert conn.execute("SELECT status FROM spreadsheets WHERE id=%s", (sid,)).fetchone()[0] == "gone"


def test_upsert_item_persists_and_refreshes_rebuy_rate(conn):
    from scraper import db
    from scraper.models import Translation, WeidianListing

    def listing(rate):
        return WeidianListing(
            weidian_url="https://weidian.com/item.html?itemID=901", weidian_item_id="901",
            title_zh="t", description_zh="", price_cny=None, seller_name=None,
            image_urls=[], seller_rebuy_rate=rate,
        )

    judge = JudgeResult(True, [], None, None, None, "")
    db.upsert_item(conn, listing(61), Translation("a", ""), judge)
    assert conn.execute("SELECT seller_rebuy_rate FROM items").fetchone()[0] == 61
    db.upsert_item(conn, listing(58), Translation("a", ""), judge)
    assert conn.execute("SELECT seller_rebuy_rate FROM items").fetchone()[0] == 58
