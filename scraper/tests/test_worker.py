from datetime import datetime, timezone

from scraper.models import JudgeResult
from scraper.worker import RUN_HOUR_UTC, monthly_store_done, tick, weekly_run_done
from tests.conftest import requires_db
from tests.test_run import make_deps

pytestmark = requires_db

# 2026-07-13 is a Monday; 2026-07-15 is a Wednesday.
MON_9 = datetime(2026, 7, 13, RUN_HOUR_UTC, 30, tzinfo=timezone.utc)
MON_EARLY = datetime(2026, 7, 13, RUN_HOUR_UTC - 1, 0, tzinfo=timezone.utc)
WED = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
WED_9 = datetime(2026, 7, 15, RUN_HOUR_UTC, 30, tzinfo=timezone.utc)


def test_weekly_run_done_false_when_no_runs(conn):
    assert weekly_run_done(conn) is False


def test_weekly_run_done_true_after_this_weeks_run(conn):
    conn.execute("INSERT INTO scrape_runs (started_at, finished_at) VALUES (now(), now())")
    assert weekly_run_done(conn) is True


def test_tick_runs_pipeline_once_per_week(conn):
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    tick(conn, deps, now=MON_9)
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 1
    tick(conn, deps, now=WED)  # same week: guarded
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 1


def test_tick_before_monday_hour_only_promotes_requested(conn):
    calls = []
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    deps.promote_requested = lambda: calls.append(True) or 0
    tick(conn, deps, now=MON_EARLY)
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 0
    assert calls == [True]


def test_tick_catches_up_later_in_week(conn):
    """A worker that comes up mid-week with no run this week still runs."""
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    tick(conn, deps, now=WED)
    assert conn.execute("SELECT count(*) FROM scrape_runs").fetchone()[0] == 1


def test_weekly_guard_ignores_store_runs(conn):
    conn.execute("INSERT INTO scrape_runs (started_at, finished_at, kind) VALUES (now(), now(), 'store')")
    assert weekly_run_done(conn) is False  # a store run doesn't satisfy the weekly guard


def test_monthly_guard_ignores_reddit_runs(conn):
    conn.execute("INSERT INTO scrape_runs (started_at, finished_at, kind) VALUES (now(), now(), 'reddit')")
    assert monthly_store_done(conn) is False  # a reddit run doesn't satisfy the monthly guard


def test_tick_runs_store_crawl_once_per_month(conn, monkeypatch):
    import scraper.worker as w

    calls = []

    def fake_crawl(c):
        calls.append(True)
        c.execute("INSERT INTO scrape_runs (started_at, finished_at, kind) VALUES (now(), now(), 'store')")

    monkeypatch.setattr(w, "run_store_crawl", fake_crawl)
    deps = make_deps([], JudgeResult(True, [], None, None, None, ""))
    # weekly already done -> tick falls through to the monthly store branch
    conn.execute("INSERT INTO scrape_runs (started_at, finished_at, kind) VALUES (now(), now(), 'reddit')")
    tick(conn, deps, now=WED_9)
    assert calls == [True]
    tick(conn, deps, now=WED_9)  # same month: guarded
    assert calls == [True]
