"""Always-on worker: 10s promotion polling + internal daily pipeline schedule."""

import logging
import os
import time
from datetime import datetime, timezone

from . import db
from .run import build_default_deps, load_env_file, run_pipeline

logger = logging.getLogger(__name__)

DAILY_HOUR_UTC = 9
POLL_SECONDS = 10
REQUEST_BATCH = 10


def daily_run_done(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM scrape_runs WHERE started_at >= date_trunc('day', now()) LIMIT 1"
    ).fetchone()
    return row is not None


def tick(conn, deps, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if now.hour >= DAILY_HOUR_UTC and not daily_run_done(conn):
        logger.info("worker: starting daily pipeline run")
        try:
            run_pipeline(conn, deps)
        except Exception:
            logger.error("daily run failed", exc_info=True)  # recorded in scrape_runs; guard holds for today
    else:
        deps.promote_requested()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    conn = db.get_conn(os.environ["DATABASE_URL"])
    deps = build_default_deps(conn)
    logger.info("worker started: daily run at %02d:00 UTC, %ss promotion polling", DAILY_HOUR_UTC, POLL_SECONDS)
    while True:
        try:
            tick(conn, deps)
        except Exception:
            logger.error("worker tick failed", exc_info=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
