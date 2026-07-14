"""Weidian listing revalidation.

revalidate_all re-checks every tracked item's liveness and updates its
status accordingly. To guard against a mass false-positive (e.g. a Weidian
outage or a detection regression making every listing look dead), decisions
are computed in a first pass without writing anything. If the number of
planned deactivations exceeds a circuit-breaker threshold
(max(3, 40% of items that were 'active' at the start of the run)), the
breaker trips: an ERROR is logged, no deactivations are applied for that
run, and 0 is returned. Revivals and touch_validated updates for
definitive (non-UNKNOWN) results are still applied even when the breaker
trips. Per-item write failures are isolated and do not abort the rest of
the run.
"""

import logging

from . import db
from .weidian import Liveness, detect_liveness, fetch_lightweight, fetch_rendered

logger = logging.getLogger(__name__)


def decide_status(liveness: Liveness, current_status: str) -> str | None:
    if liveness is Liveness.DEAD and current_status == "active":
        return "inactive"
    if liveness is Liveness.LIVE and current_status == "inactive":
        return "active"
    return None


def check_liveness(url: str, fetch=fetch_lightweight, render=fetch_rendered) -> Liveness:
    try:
        html, status = fetch(url)
        liveness = detect_liveness(html, status)
        if liveness is Liveness.UNKNOWN and render is not None:
            html, status = render(url)
            liveness = detect_liveness(html, status)
        return liveness
    except Exception:
        logger.warning("liveness check failed for %s; leaving status unchanged", url, exc_info=True)
        return Liveness.UNKNOWN


def revalidate_all(conn, fetch=fetch_lightweight, render=fetch_rendered) -> int:
    items = db.get_items_for_validation(conn)
    active_count = sum(1 for _, _, status in items if status == "active")

    # Pass 1: decide what to do for each item without writing anything.
    decisions = []
    for item_id, url, current_status in items:
        try:
            liveness = check_liveness(url, fetch=fetch, render=render)
            new_status = decide_status(liveness, current_status)
            decisions.append((item_id, url, new_status, liveness))
        except Exception:
            logger.warning(
                "revalidation failed for item_id=%s url=%s; skipping", item_id, url, exc_info=True
            )

    planned_deactivations = sum(1 for _, _, new_status, _ in decisions if new_status == "inactive")
    threshold = max(3, int(0.4 * active_count))
    breaker_tripped = planned_deactivations > threshold
    if breaker_tripped:
        logger.error(
            "revalidate_all circuit breaker tripped: %d planned deactivations exceeds "
            "threshold %d (active_count=%d); applying no deactivations this run",
            planned_deactivations,
            threshold,
            active_count,
        )

    # Pass 2: apply decisions, isolating per-item write failures.
    deactivated = 0
    for item_id, url, new_status, liveness in decisions:
        try:
            if new_status == "inactive":
                if breaker_tripped:
                    continue
                db.set_item_status(conn, item_id, new_status)
                deactivated += 1
            elif new_status == "active":
                db.set_item_status(conn, item_id, new_status)
            elif liveness is not Liveness.UNKNOWN:
                db.touch_validated(conn, item_id)
        except Exception:
            logger.warning(
                "revalidation failed for item_id=%s url=%s; skipping", item_id, url, exc_info=True
            )
    return deactivated
