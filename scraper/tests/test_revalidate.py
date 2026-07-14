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


@requires_db
def test_db_failure_on_one_item_does_not_abort_rest(conn, monkeypatch):
    from scraper import db
    from scraper.models import JudgeResult, Translation, WeidianListing

    t = Translation("t", "")
    j = JudgeResult(True, [], None, None, None, "")
    first = db.upsert_item(conn, WeidianListing("https://weidian.com/item.html?itemID=1", None, "t", "", None, None, []), t, j)
    second = db.upsert_item(conn, WeidianListing("https://weidian.com/item.html?itemID=2", None, "t", "", None, None, []), t, j)

    real_set = db.set_item_status

    def failing_set(c, item_id, status):
        if item_id == first:
            raise RuntimeError("db blip")
        real_set(c, item_id, status)

    monkeypatch.setattr("scraper.revalidate.db.set_item_status", failing_set)

    dead = "<html><body>商品已下架</body></html>"
    deactivated = revalidate_all(conn, fetch=lambda u: (dead, 200), render=lambda u: (dead, 200))

    assert deactivated == 1  # only the item whose write succeeded
    statuses = {r[0]: r[2] for r in db.get_items_for_validation(conn)}
    assert statuses[second] == "inactive"  # later item still processed
    assert statuses[first] == "active"     # failed write left it unchanged


@requires_db
def test_circuit_breaker_trips_when_all_active_items_appear_dead(conn):
    from scraper import db
    from scraper.models import JudgeResult, Translation, WeidianListing

    t = Translation("t", "")
    j = JudgeResult(True, [], None, None, None, "")
    ids = [
        db.upsert_item(
            conn,
            WeidianListing(f"https://weidian.com/item.html?itemID={i}", None, "t", "", None, None, []),
            t,
            j,
        )
        for i in range(5)
    ]

    deactivated = revalidate_all(conn, fetch=lambda u: (DEAD_HTML, 200), render=lambda u: (DEAD_HTML, 200))

    assert deactivated == 0
    statuses = {r[0]: r[2] for r in db.get_items_for_validation(conn)}
    for item_id in ids:
        assert statuses[item_id] == "active"


@requires_db
def test_circuit_breaker_does_not_trip_for_single_deactivation_among_five(conn):
    from scraper import db
    from scraper.models import JudgeResult, Translation, WeidianListing

    t = Translation("t", "")
    j = JudgeResult(True, [], None, None, None, "")
    ids = [
        db.upsert_item(
            conn,
            WeidianListing(f"https://weidian.com/item.html?itemID={i}", None, "t", "", None, None, []),
            t,
            j,
        )
        for i in range(5)
    ]

    def fetch(url):
        return (DEAD_HTML, 200) if url.endswith("itemID=0") else (LIVE_HTML, 200)

    deactivated = revalidate_all(conn, fetch=fetch, render=fetch)

    assert deactivated == 1
    statuses = {r[0]: r[2] for r in db.get_items_for_validation(conn)}
    assert statuses[ids[0]] == "inactive"
    for item_id in ids[1:]:
        assert statuses[item_id] == "active"
