"""Budgeted promotion of staged spreadsheet rows into the items catalog."""

import logging
import re

from . import db
from .config import USD_TO_CNY
from .models import JudgeResult, WeidianListing
from .weidian import Liveness, detect_liveness, parse_listing_html

logger = logging.getLogger(__name__)

# Sheet rows bypass the sentiment judge: the sheet's curation is the signal.
NEUTRAL_JUDGE = JudgeResult(
    positive_sentiment=True, red_flags=[], brand=None, category=None,
    item_name=None, quality_summary="",
)

_NUM = re.compile(r"\d+(?:\.\d+)?")


def sheet_price_cny(price_raw: str | None, currency: str | None) -> float | None:
    if not price_raw or currency not in ("CNY", "USD"):
        return None
    match = _NUM.search(price_raw)
    if not match:
        return None
    value = float(match.group(0))
    return value if currency == "CNY" else round(value * USD_TO_CNY, 2)


def _promote_weidian(conn, row: dict, fetch_page, translate) -> int | None:
    html, status = fetch_page(row["product_url"])
    if detect_liveness(html, status) is not Liveness.LIVE:
        db.mark_row_error(conn, row["id"], "not live at promotion")
        return None
    listing = parse_listing_html(html, row["product_url"])
    translation = translate(listing, row.get("name") or "")
    return db.upsert_item(conn, listing, translation, NEUTRAL_JUDGE)


def _promote_taobao(conn, row: dict, translate) -> int:
    # No taobao page scraping (login-walled): the sheet's own data is the listing.
    listing = WeidianListing(
        weidian_url=row["product_url"], weidian_item_id=None,
        title_zh=row.get("name") or "", description_zh="",
        price_cny=None, seller_name=None, image_urls=[],
    )
    translation = translate(listing, row.get("name") or "")
    return db.upsert_sheet_item(
        conn, {**row, "price_cny": sheet_price_cny(row.get("price_raw"), row.get("currency"))}, translation
    )


def promote_rows(conn, fetch_page, translate, budget: int = 200, requested_only: bool = False) -> int:
    promoted = 0
    for row in db.rows_to_promote(conn, budget, requested_only=requested_only):
        try:
            if row["platform"] == "weidian":
                item_id = _promote_weidian(conn, row, fetch_page, translate)
            else:
                item_id = _promote_taobao(conn, row, translate)
            if item_id is not None:
                db.mark_row_promoted(conn, row["id"], item_id)
                promoted += 1
        except Exception as e:
            logger.warning("promotion failed for row %s", row["id"], exc_info=True)
            db.mark_row_error(conn, row["id"], f"{type(e).__name__}: {e}")
    return promoted
