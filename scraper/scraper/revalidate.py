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
    deactivated = 0
    for item_id, url, current_status in db.get_items_for_validation(conn):
        try:
            liveness = check_liveness(url, fetch=fetch, render=render)
            new_status = decide_status(liveness, current_status)
            if new_status is not None:
                db.set_item_status(conn, item_id, new_status)
                if new_status == "inactive":
                    deactivated += 1
            elif liveness is not Liveness.UNKNOWN:
                db.touch_validated(conn, item_id)
        except Exception:
            logger.warning(
                "revalidation failed for item_id=%s url=%s; skipping", item_id, url, exc_info=True
            )
    return deactivated
