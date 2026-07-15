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
