import re
from urllib.parse import parse_qs, unquote, urlparse

_HOST = r"(?:^|[./])weidian\.com"
_PATTERNS = [
    re.compile(_HOST + r"/item\.html\?[^\s\"'<>()\[\]]*?itemID=(\d+)", re.I),
    re.compile(_HOST + r"/items?/(\d+)", re.I),
]


def canonical_url(item_id: str) -> str:
    return f"https://weidian.com/item.html?itemID={item_id}"


def extract_item_ids(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            matches.append((match.start(), match.group(1)))
    matches.sort(key=lambda pair: pair[0])

    ids: list[str] = []
    for _, item_id in matches:
        if item_id not in ids:
            ids.append(item_id)
    return ids


def extract_weidian_urls(text: str) -> list[str]:
    return [canonical_url(i) for i in extract_item_ids(text)]


_LINK_TOKEN = re.compile(r"https?://\S+|\S*weidian\.com\S*", re.I)

_SHEET_KEY = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})", re.I)
_TAOBAO_ID = re.compile(r"(?:^|[./])(?:item\.)?taobao\.com/item\.htm\?[^\s\"'<>]*?\bid=(\d+)", re.I)
_AGENT_HOSTS = ("cnfans.com", "acbuy.com", "mulebuy.com", "allchinabuy.com", "superbuy.com", "kakobuy.com")
_AGENT_PLATFORMS = {
    "weidian": "weidian", "wd": "weidian",
    "taobao": "taobao", "tb": "taobao",
}


def extract_urls_with_context(chunks: list[str]) -> list[tuple[str, str]]:
    """Map each URL to the comment line that mentions it.

    Link-wall comments are usually one item per line ("Hellstar hoodie: <url>",
    or the label on the line above a bare URL) — the line is the per-item
    classification signal that joining everything into one blob destroys.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for chunk in chunks:
        # preceding: non-empty lines since the last URL line — the item's label
        # lives here, possibly behind connector lines like "w2c:" or a rating.
        preceding: list[str] = []
        for line in chunk.splitlines():
            line = line.strip()
            urls = extract_weidian_urls(line)
            if not urls:
                if line:
                    preceding.append(line)
                continue
            has_own_label = bool(_LINK_TOKEN.sub("", line).strip(" \t:->|·•"))
            if has_own_label or not preceding:
                context = line
            else:
                context = "\n".join([*preceding[-3:], line])
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    pairs.append((url, context))
            preceding = []
    return pairs


def extract_sheet_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in _SHEET_KEY.finditer(text or ""):
        if match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def canonical_taobao_url(item_id: str) -> str:
    return f"https://item.taobao.com/item.htm?id={item_id}"


def resolve_product_link(url: str) -> tuple[str, str] | None:
    """Resolve a raw/agent-wrapped link to (platform, canonical product URL)."""
    if not url:
        return None
    weidian_ids = extract_item_ids(url)
    if weidian_ids:
        return ("weidian", canonical_url(weidian_ids[0]))
    taobao = _TAOBAO_ID.search(url)
    if taobao:
        return ("taobao", canonical_taobao_url(taobao.group(1)))

    parsed = urlparse(url if "//" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _AGENT_HOSTS):
        return None
    params = {k.lower(): v[0] for k, v in parse_qs(parsed.query).items() if v}
    if "url" in params:
        return resolve_product_link(unquote(params["url"]))
    item_id = params.get("id")
    platform_raw = params.get("platform") or params.get("source") or params.get("shop_type") or ""
    platform = _AGENT_PLATFORMS.get(platform_raw.lower())
    if item_id and item_id.isdigit() and platform == "weidian":
        return ("weidian", canonical_url(item_id))
    if item_id and item_id.isdigit() and platform == "taobao":
        return ("taobao", canonical_taobao_url(item_id))
    return None
