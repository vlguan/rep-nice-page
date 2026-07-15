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


_LINK_TOKEN = re.compile(r"https?://\S+|\S*weidian\.com\S*", re.I)


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
