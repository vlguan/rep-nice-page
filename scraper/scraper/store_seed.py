"""Seed catalog items by crawling the vetted Weidian store list.

Each store's item grid comes from a thor.weidian.com item-list XHR carrying
id/name/img/price/sold per item, so we filter by sales and insert directly
(no per-item page render). Only NEW items (product_url not already present)
are inserted; existing Reddit-vetted items are untouched. Titles that are
still Chinese are translated to English in a batched second pass.

Invoked at worker boot when SEED_STORES is set, or via `python -m
scraper.store_seed [--commit]`.
"""
import json
import logging
import os
import pathlib
import re

import psycopg
from psycopg.types.json import Json

from .config import MODEL

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
MIN_SOLD = 5
SCROLLS = 8
LIST_APIS = ("getItemListForCommonItemSection", "getCateItemListForCommonItemSection")
STORE_FILE = pathlib.Path(__file__).parent / "data" / "weidian_stores.txt"
CJK = re.compile(r"[一-鿿]")
TRANSLATE_BATCH = 25

_AGENT_SPAM = re.compile(
    r"^.*?(?:use|via)?\s*(?:allchinabuy|mulebuy|superbuy|hoobuy|basetao|cnfans|kakobuy|"
    r"sugargoo|pandabuy|acbuy|ootdbuy|joyabuy|orientdig)\b.*?agent\s*[!！]*",
    re.I,
)
_WECHAT_SPAM = re.compile(r"(add\s*wechat|whatsapp|photo\s*album|yupoo)\b.*", re.I | re.S)


def _connect():
    return psycopg.connect(
        os.environ["DATABASE_URL"], autocommit=True,
        keepalives=1, keepalives_idle=20, keepalives_interval=10, keepalives_count=5,
    )


def clean_title(name: str) -> str:
    t = _AGENT_SPAM.sub("", name or "")
    t = _WECHAT_SPAM.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" -！!·|,")
    return t or (name or "").strip()


def _iter_items(o):
    if isinstance(o, dict):
        if "itemId" in o and "itemName" in o:
            yield o
        for v in o.values():
            yield from _iter_items(v)
    elif isinstance(o, list):
        for v in o:
            yield from _iter_items(v)


def crawl_store(page, userid: str):
    """Return (rebuy_rate|None, [item dicts]); ([]) if the store is dead/closed."""
    items: dict[str, dict] = {}

    def on_resp(resp):
        if any(a in resp.url for a in LIST_APIS):
            try:
                data = json.loads(resp.text())
            except Exception:
                return
            for it in _iter_items(data):
                iid = str(it.get("itemId") or "")
                if iid:
                    items[iid] = it

    page.on("response", on_resp)
    body = ""
    try:
        page.goto(f"https://weidian.com/?userid={userid}", wait_until="networkidle", timeout=25000)
        page.wait_for_timeout(1500)
        for _ in range(SCROLLS):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(700)
        body = page.inner_text("body")
    except Exception as e:
        logger.warning("store %s crawl error: %s", userid, e)
    finally:
        page.remove_listener("response", on_resp)

    m = re.search(r"回头率\s*(\d+)\s*%", body)
    return (int(m.group(1)) if m else None), list(items.values())


def _to_row(it: dict, rebuy):
    iid = str(it["itemId"])
    try:
        sold = int(re.sub(r"\D", "", str(it.get("sold") or "0")) or 0)
    except ValueError:
        sold = 0
    if it.get("status") != 1 or sold < MIN_SOLD:
        return None
    price = None
    if it.get("price") not in (None, ""):
        try:
            price = float(re.sub(r"[^\d.]", "", str(it["price"])) or 0) or None
        except ValueError:
            price = None
    img = it.get("itemImg")
    return {
        "product_url": f"https://weidian.com/item.html?itemID={iid}",
        "platform_item_id": iid,
        "title_zh": it.get("itemName"),
        "title_en": clean_title(it.get("itemName", "")),
        "price_cny": price,
        "image_urls": [img] if img else [],
        "seller_rebuy_rate": rebuy,
        "sold": sold,
    }


def run(commit: bool = True) -> int:
    """Crawl every store and insert new items with >= MIN_SOLD sales. Returns count."""
    from playwright.sync_api import sync_playwright

    ids = STORE_FILE.read_text().split()
    conn = _connect()

    def execute(sql, params):
        nonlocal conn
        try:
            conn.execute(sql, params)
        except psycopg.OperationalError:
            conn = _connect()
            conn.execute(sql, params)

    existing = {r[0] for r in conn.execute("SELECT product_url FROM items").fetchall()}
    logger.info("store seed: %d stores, %d items already in catalog", len(ids), len(existing))

    inserted = alive = dead = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, uid in enumerate(ids, 1):
            page = b.new_page(user_agent=UA, viewport={"width": 414, "height": 896})
            rebuy, raw = crawl_store(page, uid)
            page.close()
            alive += 1 if raw else 0
            dead += 0 if raw else 1
            for it in raw:
                r = _to_row(it, rebuy)
                if not r or r["product_url"] in existing:
                    continue
                existing.add(r["product_url"])
                if commit:
                    execute(
                        """
                        INSERT INTO items (product_url, platform_item_id, platform, title_zh,
                            title_en, price_cny, image_urls, seller_rebuy_rate, sold, status)
                        VALUES (%s,%s,'weidian',%s,%s,%s,%s,%s,%s,'active')
                        ON CONFLICT (product_url) DO NOTHING
                        """,
                        (r["product_url"], r["platform_item_id"], r["title_zh"], r["title_en"],
                         r["price_cny"], Json(r["image_urls"]), r["seller_rebuy_rate"], r["sold"]),
                    )
                inserted += 1
            if i % 10 == 0:
                logger.info("store seed %d/%d: alive=%d dead=%d inserted=%d", i, len(ids), alive, dead, inserted)
        b.close()
    logger.info("store seed DONE: alive=%d dead=%d inserted=%d", alive, dead, inserted)
    return inserted


def translate_titles(commit: bool = True) -> int:
    """Batch-translate item titles that still contain Chinese into English."""
    import anthropic

    conn = _connect()
    llm = anthropic.Anthropic()
    rows = [(i, t) for i, t in conn.execute(
        "SELECT id, title_en FROM items WHERE title_en IS NOT NULL").fetchall() if CJK.search(t or "")]
    logger.info("translate_titles: %d Chinese titles", len(rows))
    prompt = ("Translate these Chinese rep-fashion product titles to concise English product names. "
              "Keep brand/model names as-is. Drop seller filler, sizing spam, and emoji. "
              "Return ONLY a JSON array of {n} strings, same order.\n\nTITLES:\n{titles}")

    done = 0
    for i in range(0, len(rows), TRANSLATE_BATCH):
        chunk = rows[i:i + TRANSLATE_BATCH]
        titles = "\n".join(f"{j+1}. {t}" for j, (_, t) in enumerate(chunk))
        try:
            msg = llm.messages.create(
                model=MODEL, max_tokens=2048,
                messages=[{"role": "user", "content": prompt.format(n=len(chunk), titles=titles)}],
            )
            text = msg.content[0].text
            out = json.loads(text[text.find("["):text.rfind("]") + 1])
        except Exception as e:
            logger.warning("translate batch %d failed: %s", i // TRANSLATE_BATCH, e)
            continue
        if not isinstance(out, list) or len(out) != len(chunk):
            continue
        for (item_id, _), en in zip(chunk, out):
            en = (en or "").strip()
            if en and commit:
                conn.execute("UPDATE items SET title_en = %s WHERE id = %s", (en, item_id))
                done += 1
    logger.info("translate_titles DONE: updated=%d", done)
    return done


def main() -> None:
    import argparse

    from .run import load_env_file

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--translate-only", action="store_true")
    args = ap.parse_args()
    if not args.translate_only:
        run(commit=args.commit)
    translate_titles(commit=args.commit)


if __name__ == "__main__":
    main()
