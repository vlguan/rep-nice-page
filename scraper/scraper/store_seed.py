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
SCROLLS = 16
LIST_APIS = ("getItemListForCommonItemSection", "getCateItemListForCommonItemSection")
STORE_JSON = pathlib.Path(__file__).parent / "data" / "weidian_stores.json"
CJK = re.compile(r"[一-鿿]")
TRANSLATE_BATCH = 25
CATEGORIES = ("clothing", "jewelry", "shoes", "accessory", "luggage")
STYLES = (
    "gorpcore", "hypebeast", "athleisure", "old money", "luxury", "minimalist",
    "alt", "opium", "goth",
)
STYLE_GUIDE = (
    "- gorpcore: outdoor/technical — The North Face, Arc'teryx, Salomon, Patagonia, Nike ACG, Stone Island\n"
    "- hypebeast: loud streetwear/designer — Supreme, BAPE, Off-White, Chrome Hearts, Amiri, Gallery Dept, Hellstar, Denim Tears\n"
    "- athleisure: sportswear/gym — Nike, Adidas, Jordan, Lululemon, Essentials tracksuits\n"
    "- old money: prep/classic — Ralph Lauren, Zegna, Brooks Brothers, Lacoste, J.Crew\n"
    "- luxury: high-fashion houses — Louis Vuitton, Gucci, Chanel, Dior, Prada, Balenciaga\n"
    "- minimalist: plain basics — Fear of God Essentials, Uniqlo-style, plain tees\n"
    "- alt: punk/emo/skater/scene — band tees, plaid & flannel, chains, Dickies, Thrasher, checkerboard, e-boy/e-girl layering (accessible mainstream-alt)\n"
    "- opium: Playboi Carti/Opium rockstar-grunge — distressed skinny or baggy denim, studded belts, leather, vampire-punk edge; Chrome Hearts, Vlone, Enfants Riches Déprimés, Hysteric Glamour, Rick Owens boots (grungy and destroyed, not clean)\n"
    "- goth: dark avant-garde/darkwear — head-to-toe black, draped silhouettes, platform & combat boots, leather; Rick Owens, Julius, Guidi, Yohji-style black (monochrome, refined-dark)"
)


def _stores() -> list[dict]:
    return json.loads(STORE_JSON.read_text())

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

    ids = [s["userid"] for s in _stores()]
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

    inserted = tagged = alive = dead = 0
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
                if not r:
                    continue
                if r["product_url"] in existing:
                    if commit:  # backfill the shop link on an already-seeded item
                        execute("UPDATE items SET shop_userid=%s WHERE product_url=%s AND shop_userid IS NULL",
                                (uid, r["product_url"]))
                        tagged += 1
                    continue
                existing.add(r["product_url"])
                if commit:
                    execute(
                        """
                        INSERT INTO items (product_url, platform_item_id, platform, title_zh,
                            title_en, price_cny, image_urls, seller_rebuy_rate, sold, shop_userid, status)
                        VALUES (%s,%s,'weidian',%s,%s,%s,%s,%s,%s,%s,'active')
                        ON CONFLICT (product_url) DO NOTHING
                        """,
                        (r["product_url"], r["platform_item_id"], r["title_zh"], r["title_en"],
                         r["price_cny"], Json(r["image_urls"]), r["seller_rebuy_rate"], r["sold"], uid),
                    )
                inserted += 1
            if i % 10 == 0:
                logger.info("store seed %d/%d: alive=%d dead=%d inserted=%d tagged=%d",
                            i, len(ids), alive, dead, inserted, tagged)
        b.close()
    logger.info("store seed DONE: alive=%d dead=%d inserted=%d shop_tagged=%d", alive, dead, inserted, tagged)
    return inserted


def translate_titles(commit: bool = True) -> int:
    """Batch-translate item titles that still contain Chinese into English."""
    import anthropic

    conn = _connect()
    llm = anthropic.Anthropic()
    rows = [(i, t) for i, t in conn.execute(
        "SELECT id, title_en FROM items WHERE title_en IS NOT NULL AND status='active'").fetchall() if CJK.search(t or "")]
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


def seed_stores(commit: bool = True) -> int:
    """Upsert the vetted-store directory (userid, name, note) into `stores`."""
    conn = _connect()
    n = 0
    for s in _stores():
        if commit:
            conn.execute(
                "INSERT INTO stores (userid, name, note) VALUES (%s,%s,%s) "
                "ON CONFLICT (userid) DO UPDATE SET name=EXCLUDED.name, note=EXCLUDED.note",
                (s["userid"], s.get("name"), s.get("note")),
            )
        n += 1
    logger.info("seed_stores: %d stores upserted", n)
    return n


def classify_items(commit: bool = True, reclassify: bool = False) -> int:
    """Batch-classify unclassified items' brand + category from their English title.

    Normally only tags items with no category yet. Pass reclassify=True to also
    re-open items already tagged 'accessory' or 'luggage' — a targeted pass for
    splitting travel cases out of the accessory bucket (and correcting the
    luggage bucket) without re-touching shoes/clothing/jewelry, where luggage
    never hides. category is only overwritten when the model returns a valid
    value, so unsure items keep their label.
    """
    import anthropic

    conn = _connect()
    llm = anthropic.Anthropic()
    where = "title_en IS NOT NULL AND status='active' AND "
    where += "(category IS NULL OR category IN ('accessory','luggage'))" if reclassify else "category IS NULL"
    rows = conn.execute(f"SELECT id, title_en FROM items WHERE {where}").fetchall()
    logger.info("classify_items: %d items (reclassify=%s)", len(rows), reclassify)
    prompt = (
        "For each rep-fashion product title, give its brand and category. "
        "category MUST be exactly one of: clothing, jewelry, shoes, accessory, luggage. "
        "Use luggage ONLY for travel cases: suitcases, carry-ons, trolley/hard cases, weekender & "
        "travel duffel bags, and garment bags. Backpacks, totes, handbags, and crossbody/shoulder bags "
        "are accessory, NOT luggage. "
        "brand is the main brand (Nike, Yeezy, Supreme, ...) or null if unclear. "
        'Return ONLY a JSON array of {n} objects [{{"brand":..,"category":..}}], same order.\n\nTITLES:\n{titles}'
    )
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
            logger.warning("classify batch %d failed: %s", i // TRANSLATE_BATCH, e)
            continue
        if not isinstance(out, list) or len(out) != len(chunk):
            continue
        for (item_id, _), o in zip(chunk, out):
            if not isinstance(o, dict):
                continue
            cat = o.get("category") if o.get("category") in CATEGORIES else None
            brand = o.get("brand")
            brand = brand.strip() or None if isinstance(brand, str) else None
            if commit and (cat or brand):
                conn.execute(
                    "UPDATE items SET category=COALESCE(%s,category), brand=COALESCE(%s,brand) WHERE id=%s",
                    (cat, brand, item_id),
                )
                done += 1
    logger.info("classify_items DONE: updated=%d", done)
    return done


def classify_style(commit: bool = True, reclassify: bool = False) -> int:
    """Batch-tag items with a style aesthetic (gorpcore, hypebeast, ...).

    Normally only tags unstyled items (style IS NULL). Pass reclassify=True for a
    one-off pass that re-evaluates every active item against the full guide;
    labels are only overwritten when the model returns a confident (non-null)
    style, so unsure items keep their existing label.
    """
    import anthropic

    conn = _connect()
    llm = anthropic.Anthropic()

    def db(sql, params=None, fetch=False):
        # reconnect-and-retry once: the long run outlives the DB proxy's idle timeout
        nonlocal conn
        try:
            cur = conn.execute(sql, params or ())
        except psycopg.OperationalError:
            conn = _connect()
            cur = conn.execute(sql, params or ())
        return cur.fetchall() if fetch else None

    where = "title_en IS NOT NULL AND status='active'"
    if not reclassify:
        where += " AND style IS NULL"
    rows = db(f"SELECT id, title_en, brand FROM items WHERE {where}", fetch=True)
    logger.info("classify_style: %d items to evaluate", len(rows))
    prompt = (
        "Classify each rep-fashion product into exactly ONE style aesthetic, or null if unclear.\n"
        f"Styles:\n{STYLE_GUIDE}\n"
        "Return ONLY a JSON array of {n} values (a style string or null), same order.\n\nITEMS:\n{items}"
    )
    done = 0
    for i in range(0, len(rows), TRANSLATE_BATCH):
        chunk = rows[i:i + TRANSLATE_BATCH]
        lines = "\n".join(
            f"{j+1}. {t}" + (f" (brand: {br})" if br else "") for j, (_, t, br) in enumerate(chunk)
        )
        try:
            msg = llm.messages.create(
                model=MODEL, max_tokens=1024,
                messages=[{"role": "user", "content": prompt.format(n=len(chunk), items=lines)}],
            )
            text = msg.content[0].text
            out = json.loads(text[text.find("["):text.rfind("]") + 1])
        except Exception as e:
            logger.warning("style batch %d failed: %s", i // TRANSLATE_BATCH, e)
            continue
        if not isinstance(out, list) or len(out) != len(chunk):
            continue
        for (item_id, _, _), s in zip(chunk, out):
            st = s.strip().lower() if isinstance(s, str) else None
            st = st if st in STYLES else None
            if commit and st:
                db("UPDATE items SET style=%s WHERE id=%s", (st, item_id))
                done += 1
    logger.info("classify_style DONE: updated=%d", done)
    return done


def prune_nonfashion(commit: bool = True) -> int:
    """Deactivate store-seeded items that aren't wearable/carryable fashion.

    Rep shops also sell packaging, shipping fees, toothbrushes, mystery boxes,
    etc. An LLM keep/drop pass soft-deletes those (status='inactive', reversible).
    Only touches store-seeded items, never Reddit-vetted ones.
    """
    import anthropic

    conn = _connect()
    llm = anthropic.Anthropic()
    rows = conn.execute(
        "SELECT id, title_en FROM items "
        "WHERE shop_userid IS NOT NULL AND status='active' AND title_en IS NOT NULL"
    ).fetchall()
    logger.info("prune_nonfashion: judging %d store items", len(rows))
    prompt = (
        "Each line is a product from a rep-fashion store. For each, answer 'keep' if it is an actual "
        "WEARABLE or CARRYABLE fashion item (clothing, shoes, bag, luggage/suitcase/carry-on, jewelry, "
        "watch, belt, hat, sunglasses, scarf, gloves, socks), or 'drop' if it is NOT fashion (shipping/"
        "postage fee, packaging, box, kraft "
        "bag, toothbrush, phone case, keychain, electronics, home goods, food, tools, mystery/blind box, "
        "freebie, sticker, price adjustment). Return ONLY a JSON array of {n} strings ('keep'|'drop'), "
        "same order.\n\nITEMS:\n{items}"
    )
    dropped = 0
    for i in range(0, len(rows), TRANSLATE_BATCH):
        chunk = rows[i:i + TRANSLATE_BATCH]
        lines = "\n".join(f"{j+1}. {t}" for j, (_, t) in enumerate(chunk))
        try:
            msg = llm.messages.create(
                model=MODEL, max_tokens=1024,
                messages=[{"role": "user", "content": prompt.format(n=len(chunk), items=lines)}],
            )
            text = msg.content[0].text
            out = json.loads(text[text.find("["):text.rfind("]") + 1])
        except Exception as e:
            logger.warning("prune batch %d failed: %s", i // TRANSLATE_BATCH, e)
            continue
        if not isinstance(out, list) or len(out) != len(chunk):
            continue
        for (item_id, _), v in zip(chunk, out):
            if isinstance(v, str) and v.strip().lower() == "drop" and commit:
                conn.execute("UPDATE items SET status='inactive' WHERE id=%s", (item_id,))
                dropped += 1
    logger.info("prune_nonfashion DONE: deactivated=%d of %d", dropped, len(rows))
    return dropped


def main() -> None:
    import argparse

    from .run import load_env_file

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--phase", choices=["all", "stores", "crawl", "prune", "translate", "classify", "style"], default="all")
    ap.add_argument("--reclassify", action="store_true",
                    help="with --phase style: re-evaluate ALL active items, not just unstyled ones; "
                         "with --phase classify: also re-open 'accessory' items (splits out luggage)")
    args = ap.parse_args()
    c = args.commit
    if args.phase in ("all", "stores"):
        seed_stores(c)
    if args.phase in ("all", "crawl"):
        run(commit=c)
    if args.phase in ("all", "prune"):
        prune_nonfashion(c)
    if args.phase in ("all", "translate"):
        translate_titles(c)
    if args.phase in ("all", "classify"):
        classify_items(c, reclassify=args.reclassify)
    if args.phase in ("all", "style"):
        classify_style(c, reclassify=args.reclassify)


if __name__ == "__main__":
    main()
