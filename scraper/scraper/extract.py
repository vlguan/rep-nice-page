import re

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
