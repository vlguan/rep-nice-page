from scraper.models import RedditPost


def test_redditpost_defaults():
    p = RedditPost(
        reddit_post_id="abc", permalink="https://reddit.com/x", title="t",
        body="", subreddit="FashionReps", score=1, num_comments=0, posted_at=0,
    )
    assert p.comments == []
