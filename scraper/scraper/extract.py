import re

_PATTERNS = [
    re.compile(r"weidian\.com/item\.html\?[^\s\"'<>()\[\]]*?itemID=(\d+)", re.I),
    re.compile(r"weidian\.com/items?/(\d+)", re.I),
]


def canonical_url(item_id: str) -> str:
    return f"https://weidian.com/item.html?itemID={item_id}"


def extract_item_ids(text: str) -> list[str]:
    ids: list[str] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            item_id = match.group(1)
            if item_id not in ids:
                ids.append(item_id)
    return ids


def extract_weidian_urls(text: str) -> list[str]:
    return [canonical_url(i) for i in extract_item_ids(text)]
