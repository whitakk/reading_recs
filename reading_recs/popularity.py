import logging
import time

import httpx

from reading_recs import db
from reading_recs.models import Article

log = logging.getLogger(__name__)

_client = httpx.Client(timeout=10, follow_redirects=True, headers={
    "User-Agent": "reading_recs/0.1 (personal RSS aggregator)"
})


def query_hn(url: str) -> dict:
    """Query HN Algolia API for engagement data on a URL."""
    try:
        resp = _client.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": url, "restrictSearchableAttributes": "url", "hitsPerPage": 5},
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            return {"comments": 0, "score": 0}
        # Take the hit with the most points
        best = max(hits, key=lambda h: h.get("points", 0) or 0)
        return {
            "comments": best.get("num_comments", 0) or 0,
            "score": best.get("points", 0) or 0,
        }
    except Exception as e:
        log.debug("HN query failed for %s: %s", url, e)
        return {"comments": 0, "score": 0}


_reddit_blocked = False


def query_reddit(url: str) -> dict:
    """Query Reddit search JSON API for engagement data on a URL."""
    global _reddit_blocked
    if _reddit_blocked:
        return {"comments": 0, "score": 0}
    try:
        resp = _client.get(
            "https://www.reddit.com/search.json",
            params={"q": f"url:{url}", "sort": "top", "limit": 5},
        )
        if resp.status_code == 429:
            log.info("Reddit rate-limited, skipping Reddit for remaining articles")
            _reddit_blocked = True
            return {"comments": 0, "score": 0}
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        if not posts:
            return {"comments": 0, "score": 0}
        best = max(posts, key=lambda p: p.get("data", {}).get("score", 0))
        d = best.get("data", {})
        return {
            "comments": d.get("num_comments", 0) or 0,
            "score": d.get("score", 0) or 0,
        }
    except Exception as e:
        log.debug("Reddit query failed for %s: %s", url, e)
        return {"comments": 0, "score": 0}


def enrich(articles: list[Article]) -> list[Article]:
    """Enrich articles with popularity signals and flag above-average ones."""
    global _reddit_blocked
    _reddit_blocked = False  # reset per run

    for i, article in enumerate(articles):
        hn = query_hn(article.url)
        time.sleep(0.1)  # light rate limiting for HN

        reddit = query_reddit(article.url)
        if not _reddit_blocked:
            time.sleep(0.5)  # Reddit rate limiting

        total_comments = article.comment_count + hn["comments"] + reddit["comments"]
        total_score = hn["score"] + reddit["score"]

        # Update rolling averages for this source
        db.update_feed_stats(article.source, total_comments, total_score)
        avg_comments, avg_score, _ = db.get_feed_stats(article.source)

        article.comment_count = total_comments
        article.is_above_average = (
            total_comments > avg_comments or total_score > avg_score
        )

        if (i + 1) % 10 == 0:
            log.info("Enriched %d/%d articles", i + 1, len(articles))

    above_avg_count = sum(1 for a in articles if a.is_above_average)
    log.info("Popularity: %d/%d articles flagged above average", above_avg_count, len(articles))
    return articles
