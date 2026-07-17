"""Always-on worker: 10s promotion polling + internal weekly pipeline schedule."""

import logging
import os
import time
from datetime import datetime, timezone

from . import db
from .run import build_default_deps, load_env_file, run_pipeline

logger = logging.getLogger(__name__)

RUN_WEEKDAY = 0  # Monday (Python weekday(): Monday=0), matching the top?t=week window
RUN_HOUR_UTC = 9
POLL_SECONDS = 10
REQUEST_BATCH = 10


def weekly_run_done(conn) -> bool:
    """True if the pipeline already ran this week (Postgres week starts Monday)."""
    row = conn.execute(
        "SELECT 1 FROM scrape_runs WHERE started_at >= date_trunc('week', now()) LIMIT 1"
    ).fetchone()
    return row is not None


def _due(now: datetime) -> bool:
    """Due once we're past Monday 09:00 UTC; later weekdays catch up a missed run."""
    if now.weekday() > RUN_WEEKDAY:
        return True
    return now.weekday() == RUN_WEEKDAY and now.hour >= RUN_HOUR_UTC


def tick(conn, deps, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if _due(now) and not weekly_run_done(conn):
        logger.info("worker: starting weekly pipeline run")
        try:
            run_pipeline(conn, deps)
        except Exception:
            logger.error("weekly run failed", exc_info=True)  # recorded in scrape_runs; guard holds for the week
    else:
        deps.promote_requested()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    conn = db.get_conn(os.environ["DATABASE_URL"])
    deps = build_default_deps(conn)
    # One-shot: seed store items + translate titles when SEED_STORES is set.
    # Runs server-side so it survives a closed laptop; unset the var afterward.
    if os.environ.get("SEED_STORES"):
        try:
            from . import store_seed
            logger.info("SEED_STORES set: stores + crawl + translate + classify")
            store_seed.seed_stores(commit=True)
            store_seed.run(commit=True)
            store_seed.translate_titles(commit=True)
            store_seed.classify_items(commit=True)
        except Exception:
            logger.error("store seed failed", exc_info=True)
    logger.info("worker started: weekly run Mondays %02d:00 UTC, %ss promotion polling", RUN_HOUR_UTC, POLL_SECONDS)
    while True:
        try:
            tick(conn, deps)
        except Exception:
            logger.error("worker tick failed", exc_info=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
