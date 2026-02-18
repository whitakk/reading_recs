import logging
from datetime import datetime, timezone, timedelta

import feedparser
import httpx
from bs4 import BeautifulSoup

from reading_recs.config import FEEDS_PATH, FEED_LOOKBACK_DAYS, FEED_MAX_ENTRIES
from reading_recs.models import Article

log = logging.getLogger(__name__)

_client = httpx.Client(timeout=15, follow_redirects=True, headers={
    "User-Agent": "reading_recs/0.1 (personal RSS aggregator)"
})


def parse_feeds() -> list[dict]:
    """Parse feeds.txt, return list of {url, title, is_aggregator}."""
    feeds = []
    for line in FEEDS_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            title, url = line.split("|", 1)
            title, url = title.strip(), url.strip()
        else:
            url = line
            title = url
        feeds.append({"url": url, "title": title, "is_aggregator": False})
    return feeds


def fetch_full_text(url: str) -> str | None:
    """Attempt to fetch and extract article body text."""
    try:
        resp = _client.get(url)
        resp.raise_for_status()
    except Exception as e:
        log.debug("Failed to fetch %s: %s", url, e)
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Try <article>, then largest <div>, then <body>
    article_tag = soup.find("article")
    if article_tag:
        return article_tag.get_text(separator=" ", strip=True)

    divs = soup.find_all("div")
    if divs:
        largest = max(divs, key=lambda d: len(d.get_text()))
        text = largest.get_text(separator=" ", strip=True)
        if len(text) > 200:
            return text

    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)

    return None


def _extract_aggregator_links(html: str) -> list[str]:
    """Extract outbound article URLs from an aggregator entry's HTML summary."""
    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "comment" not in href.lower():
            urls.append(href)
    return urls


def _get_comment_count(entry) -> int:
    """Extract comment count from RSS entry if available."""
    # slash:comments (used by many feeds)
    if hasattr(entry, "slash_comments"):
        try:
            return int(entry.slash_comments)
        except (ValueError, TypeError):
            pass
    return 0


def _entry_published(entry) -> datetime | None:
    """Return entry publish time as UTC datetime, or None if unavailable."""
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if t:
        return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_feeds() -> list[Article]:
    """Fetch all feeds from feeds.txt and return Article objects."""
    feeds = parse_feeds()
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=FEED_LOOKBACK_DAYS)

    for feed_info in feeds:
        log.info("Fetching feed: %s", feed_info["title"])
        try:
            parsed = feedparser.parse(feed_info["url"])
        except Exception as e:
            log.warning("Failed to parse feed %s: %s", feed_info["url"], e)
            continue

        for entry in parsed.entries[:FEED_MAX_ENTRIES]:
            pub = _entry_published(entry)
            if pub and pub < cutoff:
                continue

            if feed_info["is_aggregator"]:
                # For aggregator feeds, extract linked URLs as separate articles
                summary_html = getattr(entry, "summary", "")
                linked_urls = _extract_aggregator_links(summary_html)
                for url in linked_urls:
                    articles.append(Article(
                        url=url,
                        title=getattr(entry, "title", url),
                        source=feed_info["title"],
                        text="",  # will be filled by full-text fetch
                    ))
            else:
                link = getattr(entry, "link", None)
                if not link:
                    continue
                summary = getattr(entry, "summary", "")
                # Strip HTML from summary
                if summary:
                    summary = BeautifulSoup(summary, "lxml").get_text(separator=" ", strip=True)

                articles.append(Article(
                    url=link,
                    title=getattr(entry, "title", link),
                    source=feed_info["title"],
                    text=summary,
                    comment_count=_get_comment_count(entry),
                ))

    return articles


def fetch_all() -> list[Article]:
    """Full fetch pipeline: get feeds, then fill in missing full text."""
    articles = fetch_feeds()

    # Deduplicate by URL
    seen = set()
    deduped = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            deduped.append(a)
    articles = deduped

    # Fetch full text for articles with short excerpts
    for article in articles:
        word_count = len(article.text.split()) if article.text else 0
        if word_count < 100:
            full_text = fetch_full_text(article.url)
            if full_text:
                article.text = full_text
            else:
                article.limited_data = True

    return articles
