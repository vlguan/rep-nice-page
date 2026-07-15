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
