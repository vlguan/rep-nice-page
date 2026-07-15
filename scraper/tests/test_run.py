from scraper.models import JudgeResult, RedditPost, Translation
from scraper.run import Deps, run_pipeline
from tests.conftest import requires_db

pytestmark = requires_db

LIVE_HTML = (
    '<html><head><meta property="og:title" content="帽衫"/>'
    '<meta property="og:description" content="重磅"/>'
    '<meta property="og:image" content="https://si.geilicdn.com/a.jpg"/></head><body></body></html>'
)


def make_post(pid, body, score=100):
    return RedditPost(
        reddit_post_id=pid, permalink=f"https://reddit.com/{pid}", title=f"post {pid}",
        body=body, subreddit="FashionReps", score=score, num_comments=1, posted_at=1752300000,
    )


def make_deps(posts, judge_result):
    return Deps(
        discover=lambda: posts,
        fetch_comments=lambda post: ["nice quality"],
        judge=lambda post: judge_result,
        fetch_page=lambda url: (LIVE_HTML, 200),
        translate=lambda listing, context: Translation("CH hoodie", "heavy fabric"),
        revalidate=lambda conn: 0,
    )


def test_positive_post_creates_item(conn):
    posts = [make_post("p1", "https://weidian.com/item.html?itemID=111")]
    judge = JudgeResult(True, [], "Chrome Hearts", "clothing", "hoodie", "good")
    stats = run_pipeline(conn, make_deps(posts, judge))
    assert stats.posts_seen == 1
    assert stats.items_added == 1
    row = conn.execute("SELECT title_en, status FROM items").fetchone()
    assert row == ("CH hoodie", "active")
    assert conn.execute("SELECT count(*) FROM item_mentions").fetchone()[0] == 1


def test_negative_post_records_post_but_no_item(conn):
    posts = [make_post("p2", "https://weidian.com/item.html?itemID=222")]
    judge = JudgeResult(False, [], None, None, None, "shilly")
    stats = run_pipeline(conn, make_deps(posts, judge))
    assert stats.items_added == 0
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] == "negative"
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 0


def test_red_flagged_post_marked_flagged(conn):
    posts = [make_post("p3", "https://weidian.com/item.html?itemID=333")]
    judge = JudgeResult(True, ["known shill"], None, None, None, "")
    run_pipeline(conn, make_deps(posts, judge))
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] == "flagged"
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 0


def test_post_without_weidian_link_recorded_and_skipped(conn):
    posts = [make_post("p4", "just haul pics")]
    deps = make_deps(posts, JudgeResult(True, [], None, None, None, ""))
    deps.judge = lambda post: (_ for _ in ()).throw(AssertionError("judge must not be called"))
    stats = run_pipeline(conn, deps)
    assert stats.items_added == 0
    assert conn.execute("SELECT sentiment FROM reddit_posts").fetchone()[0] is None


def test_already_seen_posts_skipped(conn):
    posts = [make_post("p5", "https://weidian.com/item.html?itemID=555")]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    run_pipeline(conn, make_deps(posts, judge))
    stats = run_pipeline(conn, make_deps(posts, judge))  # second run, same post
    assert stats.items_added == 0
    assert conn.execute("SELECT count(*) FROM reddit_posts").fetchone()[0] == 1


def test_one_bad_item_does_not_kill_run(conn):
    posts = [
        make_post("p6", "https://weidian.com/item.html?itemID=666"),
        make_post("p7", "https://weidian.com/item.html?itemID=777"),
    ]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    deps = make_deps(posts, judge)

    def flaky_fetch(url):
        if "666" in url:
            raise TimeoutError("weidian down")
        return LIVE_HTML, 200

    deps.fetch_page = flaky_fetch
    stats = run_pipeline(conn, deps)
    assert stats.items_added == 1


def test_limit_caps_candidate_posts(conn):
    posts = [
        make_post(f"p{i}", f"https://weidian.com/item.html?itemID=10{i}") for i in range(10)
    ]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    stats = run_pipeline(conn, make_deps(posts, judge), limit=3)
    assert stats.items_added == 3


def test_run_recorded(conn):
    posts = [make_post("p8", "https://weidian.com/item.html?itemID=888")]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    run_pipeline(conn, make_deps(posts, judge))
    row = conn.execute(
        "SELECT posts_seen, items_added, items_deactivated, error FROM scrape_runs"
    ).fetchone()
    assert row == (1, 1, 0, None)


def test_limit_stops_examining_and_leaves_rest_unrecorded(conn):
    posts = [
        make_post("pa", "no link here"),
        make_post("pb", "https://weidian.com/item.html?itemID=901"),
        make_post("pc", "https://weidian.com/item.html?itemID=902"),
        make_post("pd", "also no link"),
        make_post("pe", "https://weidian.com/item.html?itemID=903"),
    ]
    judge = JudgeResult(True, [], None, "clothing", None, "")
    stats = run_pipeline(conn, make_deps(posts, judge), limit=2)
    assert stats.items_added == 2
    assert stats.posts_seen == 3  # pa, pb, pc examined; pd, pe never examined
    recorded = {r[0] for r in conn.execute("SELECT reddit_post_id FROM reddit_posts").fetchall()}
    assert recorded == {"pa", "pb", "pc"}  # pd/pe unrecorded -> fresh next run

    stats2 = run_pipeline(conn, make_deps(posts, judge))  # unlimited follow-up run
    assert stats2.items_added == 1  # pe ingested now
    recorded2 = {r[0] for r in conn.execute("SELECT reddit_post_id FROM reddit_posts").fetchall()}
    assert recorded2 == {"pa", "pb", "pc", "pd", "pe"}


def test_aborted_run_records_error_and_reraises(conn):
    import pytest

    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    deps.discover = lambda: (_ for _ in ()).throw(RuntimeError("reddit down"))
    with pytest.raises(RuntimeError):
        run_pipeline(conn, deps)
    row = conn.execute("SELECT error FROM scrape_runs").fetchone()
    assert row[0] == "RuntimeError: reddit down"


def test_load_env_file_sets_without_override(tmp_path, monkeypatch):
    from scraper.run import load_env_file

    env = tmp_path / ".env"
    env.write_text('REDDIT_CLIENT_ID=abc123\n# comment\nREDDIT_CLIENT_SECRET="s3cret"\nEXISTING=filevalue\n')
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("EXISTING", "shellvalue")
    load_env_file(env)
    import os

    assert os.environ["REDDIT_CLIENT_ID"] == "abc123"
    assert os.environ["REDDIT_CLIENT_SECRET"] == "s3cret"
    assert os.environ["EXISTING"] == "shellvalue"  # shell wins over file


def test_translate_gets_url_context_and_its_classification_is_stored(conn):
    posts = [make_post("p10", "my summer haul QC")]
    judge = JudgeResult(True, [], "Multiple", None, None, "good haul")
    deps = make_deps(posts, judge)
    deps.fetch_comments = lambda post: [
        "W2C the Hellstar hoodie https://weidian.com/item.html?itemID=1001",
        "AMIRI jeans https://weidian.com/item.html?itemID=1002",
    ]
    contexts = []

    def translate(listing, context):
        contexts.append(context)
        brand = "Hellstar" if "Hellstar" in context else "AMIRI"
        return Translation(f"{brand} item", "d", brand=brand, category="clothing")

    deps.translate = translate
    stats = run_pipeline(conn, deps)
    assert stats.items_added == 2
    assert any("Hellstar" in c for c in contexts)
    assert any("AMIRI" in c for c in contexts)
    rows = dict(conn.execute("SELECT weidian_item_id, brand FROM items").fetchall())
    assert rows == {"1001": "Hellstar", "1002": "AMIRI"}


def test_judge_brand_used_when_translation_has_none(conn):
    posts = [make_post("p11", "https://weidian.com/item.html?itemID=1101")]
    judge = JudgeResult(True, [], "Chrome Hearts", "clothing", "hoodie", "good")
    deps = make_deps(posts, judge)
    deps.translate = lambda listing, context: Translation("hoodie", "d")
    run_pipeline(conn, deps)
    row = conn.execute("SELECT brand, category FROM items").fetchone()
    assert row == ("Chrome Hearts", "clothing")


def test_reingest_refreshes_brand_and_category(conn):
    judge = JudgeResult(True, [], "Multiple", None, None, "")
    posts = [make_post("p12", "https://weidian.com/item.html?itemID=1201")]
    deps = make_deps(posts, judge)
    deps.translate = lambda listing, context: Translation("hoodie", "d")
    run_pipeline(conn, deps)
    assert conn.execute("SELECT brand FROM items").fetchone()[0] == "Multiple"

    posts2 = [make_post("p13", "https://weidian.com/item.html?itemID=1201")]
    deps2 = make_deps(posts2, judge)
    deps2.translate = lambda listing, context: Translation(
        "hoodie", "d", brand="Hellstar", category="clothing"
    )
    run_pipeline(conn, deps2)
    row = conn.execute("SELECT brand, category FROM items").fetchone()
    assert row == ("Hellstar", "clothing")
