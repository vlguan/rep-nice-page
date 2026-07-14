from dataclasses import dataclass, field


@dataclass
class RedditPost:
    reddit_post_id: str
    permalink: str
    title: str
    body: str
    subreddit: str
    score: int
    num_comments: int
    posted_at: int  # unix epoch UTC
    comments: list[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    positive_sentiment: bool
    red_flags: list[str]        # tier-1 community callouts ONLY
    brand: str | None
    category: str | None        # clothing | jewelry | shoes | accessory
    item_name: str | None
    quality_summary: str


@dataclass
class WeidianListing:
    weidian_url: str            # canonical form
    weidian_item_id: str | None
    title_zh: str
    description_zh: str
    price_cny: float | None
    seller_name: str | None
    image_urls: list[str]


@dataclass
class Translation:
    title_en: str
    description_en: str
