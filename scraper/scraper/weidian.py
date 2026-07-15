import re
from enum import Enum

import httpx

from .extract import extract_item_ids
from .models import WeidianListing

DEAD_MARKERS = [
    "商品已下架",
    "该店铺已关闭",
    "商品不存在",
    "店铺不存在",
    "宝贝不存在",
]

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class Liveness(Enum):
    LIVE = "live"
    DEAD = "dead"
    UNKNOWN = "unknown"


def _meta(html: str, prop: str) -> str | None:
    escaped = re.escape(prop)
    patterns = (
        rf'<meta[^>]+(?:property|name)=["\']{escaped}["\'][^>]+content=["\']([^"\']*)["\']',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{escaped}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1) or None
    return None


# Titles of SPA shell / error pages that carry no product information;
# dead and nonexistent listings render with "商品详情".
GENERIC_TITLES = {"商品详情", "微店", "weidian"}


def _page_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    if not title or title.lower() in GENERIC_TITLES:
        return None
    return title


def _title_signal(html: str) -> str | None:
    # Weidian's rendered mobile pages stopped emitting og:title (2026-07);
    # fall back to the plain <title> tag, ignoring generic shell titles.
    return _meta(html, "og:title") or _page_title(html)


def detect_liveness(html: str, status_code: int) -> Liveness:
    if status_code == 404:
        return Liveness.DEAD
    if status_code >= 400:
        return Liveness.UNKNOWN
    has_dead_marker = any(marker in html for marker in DEAD_MARKERS)
    has_og_title = bool(_title_signal(html))
    if has_dead_marker and has_og_title:
        # Conflicting signals (Weidian is an SPA, so removal-notice strings can
        # appear inside <script> bundles even on live pages) — never
        # deactivate on ambiguity.
        return Liveness.UNKNOWN
    if has_dead_marker:
        return Liveness.DEAD
    if has_og_title:
        return Liveness.LIVE
    return Liveness.UNKNOWN


def parse_listing_html(html: str, url: str) -> WeidianListing:
    title = _title_signal(html)
    if not title:
        raise ValueError(f"no listing title found at {url}")

    price = None
    price_meta = _meta(html, "og:product:price:amount")
    if price_meta:
        price = float(price_meta)
    else:
        price_matches = list(re.finditer(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)', html))
        if price_matches:
            price = float(price_matches[-1].group(1))
        else:
            # Rendered mobile pages carry the price only as display text.
            yen_match = re.search(r"[¥￥]\s*(\d+(?:\.\d+)?)", html)
            if yen_match:
                price = float(yen_match.group(1))

    images: list[str] = []
    og_image = _meta(html, "og:image")
    if og_image:
        images.append(og_image)
    for match in re.finditer(r'https://si\.geilicdn\.com/[^\s"\'\\]+?\.(?:jpg|jpeg|png|webp)', html):
        if match.group(0) not in images:
            images.append(match.group(0))

    seller = _meta(html, "shop_name")
    if not seller:
        seller_match = re.search(r'"shopName"\s*:\s*"([^"]+)"', html)
        seller = seller_match.group(1) if seller_match else None

    ids = extract_item_ids(url)
    id_match = re.search(r'"itemID"\s*:\s*"?(\d+)', html)

    return WeidianListing(
        weidian_url=url,
        weidian_item_id=ids[0] if ids else (id_match.group(1) if id_match else None),
        title_zh=title,
        description_zh=_meta(html, "og:description") or "",
        price_cny=price,
        seller_name=seller,
        image_urls=images,
    )


def fetch_lightweight(url: str, timeout: float = 15.0) -> tuple[str, int]:
    resp = httpx.get(
        url,
        headers={"User-Agent": MOBILE_UA},
        follow_redirects=True,
        timeout=timeout,
    )
    return resp.text, resp.status_code


def fetch_rendered(url: str, timeout_ms: int = 30000) -> tuple[str, int]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=MOBILE_UA)
            resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # let client-side rendering settle
            return page.content(), resp.status if resp else 0
        finally:
            browser.close()
