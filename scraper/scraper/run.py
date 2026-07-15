import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from . import db
from .models import RedditPost, Translation, WeidianListing
from .weidian import Liveness, detect_liveness, parse_listing_html

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    discover: Callable[[], list[RedditPost]]
    fetch_comments: Callable[[RedditPost], list[str]]
    judge: Callable[[RedditPost], "JudgeResult"]
    fetch_page: Callable[[str], tuple[str, int]]
    translate: Callable[[WeidianListing, str], Translation]
    revalidate: Callable[..., int]
    sync_sheets: Callable[[], None]
    promote: Callable[[], int]


@dataclass
class RunStats:
    posts_seen: int = 0
    items_added: int = 0
    items_deactivated: int = 0


def _ingest_item(conn, deps: Deps, url: str, context: str, judge_result, post_row_id: int) -> bool:
    html, status = deps.fetch_page(url)
    if detect_liveness(html, status) is not Liveness.LIVE:
        logger.info("skipping %s: not live at ingest", url)
        return False
    listing = parse_listing_html(html, url)
    translation = deps.translate(listing, context)
    item_id = db.upsert_item(conn, listing, translation, judge_result)
    db.link_mention(conn, item_id, post_row_id)
    return True


def run_pipeline(conn, deps: Deps, limit: int | None = None) -> RunStats:
    """Run one discover -> judge -> ingest -> revalidate pass.

    When `limit` is set (manual smoke runs only), the run stops examining
    further posts once `limit` candidates have been processed; posts never
    examined are left unrecorded so a later unlimited run picks them up fresh,
    and `stats.posts_seen` only counts posts actually examined.
    """
    from .extract import extract_sheet_keys, extract_urls_with_context
    from .judge import should_ingest

    started_at = datetime.now(timezone.utc)
    stats = RunStats()
    error: str | None = None
    try:
        posts = deps.discover()
        seen = db.seen_post_ids(conn, [p.reddit_post_id for p in posts])
        new_posts = [p for p in posts if p.reddit_post_id not in seen]

        processed = 0
        for post in new_posts:
            if limit is not None and processed >= limit:
                break
            stats.posts_seen += 1
            try:
                post.comments = deps.fetch_comments(post)
                chunks = [f"{post.title}\n{post.body}", *post.comments]
                url_contexts = extract_urls_with_context(chunks)
                for key in extract_sheet_keys("\n".join(chunks)):
                    db.upsert_spreadsheet(
                        conn, key, f"https://docs.google.com/spreadsheets/d/{key}", None
                    )
                if not url_contexts:
                    db.insert_post(conn, post, None, None)
                    continue
                processed += 1
                judge_result = deps.judge(post)
                if judge_result.red_flags:
                    sentiment = "flagged"
                elif judge_result.positive_sentiment:
                    sentiment = "positive"
                else:
                    sentiment = "negative"
                post_row_id = db.insert_post(conn, post, sentiment, judge_result.quality_summary)
                if not should_ingest(judge_result):
                    continue
                for url, context in url_contexts:
                    try:
                        if _ingest_item(conn, deps, url, context, judge_result, post_row_id):
                            stats.items_added += 1
                    except Exception:
                        logger.warning("failed to ingest %s", url, exc_info=True)
            except Exception:
                logger.warning("failed to process post %s", post.reddit_post_id, exc_info=True)

        deps.sync_sheets()
        deps.promote()
        stats.items_deactivated = deps.revalidate(conn)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.error("pipeline aborted", exc_info=True)
        raise
    finally:
        db.record_run(
            conn, started_at, stats.posts_seen, stats.items_added,
            stats.items_deactivated, error,
        )
    return stats


def build_default_deps(conn) -> Deps:
    import anthropic
    import httpx as _httpx

    from . import judge as judge_mod
    from . import promote as promote_mod
    from . import revalidate, sheets, translate as translate_mod
    from .weidian import fetch_rendered

    llm = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    if os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"):
        from . import reddit

        http_client = reddit.oauth_client()
        discover = lambda: reddit.discover_posts(http_client)  # noqa: E731
        fetch_comments = lambda post: reddit.fetch_post_comments(http_client, post)  # noqa: E731
        logger.info("reddit transport: official OAuth API")
    else:
        from . import reddit_html

        discover = reddit_html.discover_posts
        fetch_comments = reddit_html.fetch_post_comments
        logger.info("reddit transport: scrapling/camoufox HTML (no oauth creds)")

    sheet_client = _httpx.Client()

    return Deps(
        discover=discover,
        fetch_comments=fetch_comments,
        judge=lambda post: judge_mod.judge_post(llm, post),
        fetch_page=fetch_rendered,
        translate=lambda listing, context: translate_mod.translate_listing(llm, listing, context),
        revalidate=revalidate.revalidate_all,
        sync_sheets=lambda: sheets.sync_spreadsheets(conn, llm, sheet_client),
        promote=lambda: promote_mod.promote_rows(
            conn, fetch_page=fetch_rendered,
            translate=lambda listing, context: translate_mod.translate_listing(llm, listing, context),
        ),
    )


def load_env_file(path: "pathlib.Path | None" = None) -> None:
    """Load KEY=VALUE lines from scraper/.env into os.environ (no overrides)."""
    import pathlib

    env_file = path or pathlib.Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file()
    parser = argparse.ArgumentParser(description="rep-nice-page daily pipeline")
    parser.add_argument("--limit", type=int, default=None, help="max candidate posts to process")
    args = parser.parse_args()

    conn = db.get_conn(os.environ["DATABASE_URL"])
    stats = run_pipeline(conn, build_default_deps(conn), limit=args.limit)
    logger.info(
        "done: %s new posts seen, %s items added, %s deactivated",
        stats.posts_seen, stats.items_added, stats.items_deactivated,
    )


if __name__ == "__main__":
    main()
