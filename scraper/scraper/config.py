MODEL = "claude-haiku-4-5-20251001"
USER_AGENT = "rep-nice-page/1.0 (personal aggregator)"
REQUEST_DELAY = 1.5  # seconds between Reddit requests
SUBREDDIT = "FashionReps"

# Per-listing pagination caps. Daily runs stay lean; the one-time --backfill
# pulls the full top-of-month (Reddit's pagination ceilings out near 1000).
DISCOVER_LIMIT = 300
DISCOVER_LIMIT_BACKFILL = 1000
SEARCH_LIMIT = 100  # search results per query (sheet-sharing posts are few)

# Listings pulled per run. `hot` keeps it fresh; backfill adds the heavy
# top?t=month sweep to seed the catalog. Overlap is deduplicated downstream.
DAILY_LISTINGS = ("top?t=week", "hot")
BACKFILL_LISTINGS = ("top?t=week", "top?t=month", "hot")

# Subreddit search queries run every pass to surface community W2C
# spreadsheets that never reach the top/hot listings.
SEARCH_QUERIES = ("spreadsheet", "w2c spreadsheet", "excel sheet", "haul spreadsheet")

USD_TO_CNY = 7.14  # sheet prices given in USD are stored as CNY at this rate
