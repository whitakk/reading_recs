import sqlite3
from datetime import date, datetime
from reading_recs.config import DB_PATH, DATA_DIR
from reading_recs.models import Article, ScoredArticle

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    text TEXT,
    embedding_score REAL,
    llm_score REAL,
    reason TEXT,
    recommended INTEGER DEFAULT 0,
    run_date TEXT
);

CREATE TABLE IF NOT EXISTS feed_stats (
    feed_url TEXT PRIMARY KEY,
    avg_comment_count REAL DEFAULT 0,
    avg_score REAL DEFAULT 0,
    article_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS validation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    embedding_score REAL,
    llm_score REAL,
    run_date TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    url TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    thumbs_up INTEGER,
    digest_date TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS preference_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    summary TEXT,
    feedback_count INTEGER,
    updated_at TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.close()


def get_recent_source_counts(lookback_days: int) -> dict[str, int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM articles WHERE recommended = 1 AND run_date >= date('now', ? || ' days') GROUP BY source",
        (f"-{lookback_days}",),
    ).fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def get_previously_recommended() -> set[str]:
    conn = get_conn()
    rows = conn.execute("SELECT url FROM articles WHERE recommended = 1").fetchall()
    conn.close()
    return {row[0] for row in rows}


def save_articles(scored_articles: list[ScoredArticle], recommended_urls: set[str]):
    conn = get_conn()
    today = date.today().isoformat()
    for sa in scored_articles:
        conn.execute(
            """INSERT OR REPLACE INTO articles
               (url, title, source, text, embedding_score, llm_score, reason, recommended, run_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sa.article.url,
                sa.article.title,
                sa.article.source,
                sa.article.text[:5000],
                0.0,
                sa.llm_score,
                sa.reason,
                1 if sa.article.url in recommended_urls else 0,
                today,
            ),
        )
    conn.commit()
    conn.close()


def get_feed_stats(feed_url: str) -> tuple[float, float, int]:
    conn = get_conn()
    row = conn.execute(
        "SELECT avg_comment_count, avg_score, article_count FROM feed_stats WHERE feed_url = ?",
        (feed_url,),
    ).fetchone()
    conn.close()
    if row:
        return row
    return (0.0, 0.0, 0)


def update_feed_stats(feed_url: str, comment_count: float, score: float):
    old_avg_comments, old_avg_score, count = get_feed_stats(feed_url)
    if count == 0:
        new_avg_comments = comment_count
        new_avg_score = score
    else:
        new_avg_comments = 0.9 * old_avg_comments + 0.1 * comment_count
        new_avg_score = 0.9 * old_avg_score + 0.1 * score
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO feed_stats (feed_url, avg_comment_count, avg_score, article_count)
           VALUES (?, ?, ?, ?)""",
        (feed_url, new_avg_comments, new_avg_score, count + 1),
    )
    conn.commit()
    conn.close()


# --- Feedback tables ---

def save_feedback(url: str, title: str, source: str, thumbs_up: bool, digest_date: str):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO feedback (url, title, source, thumbs_up, digest_date, synced_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (url, title, source, 1 if thumbs_up else 0, digest_date, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_all_feedback() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT url, title, source, thumbs_up, digest_date FROM feedback ORDER BY synced_at"
    ).fetchall()
    conn.close()
    return [
        {"url": r[0], "title": r[1], "source": r[2], "thumbs_up": bool(r[3]), "digest_date": r[4]}
        for r in rows
    ]


def get_feedback_count() -> int:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    conn.close()
    return count


def get_preference_summary() -> tuple[str, int] | None:
    conn = get_conn()
    row = conn.execute("SELECT summary, feedback_count FROM preference_summary WHERE id = 1").fetchone()
    conn.close()
    if row:
        return (row[0], row[1])
    return None


def save_preference_summary(summary: str, feedback_count: int):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO preference_summary (id, summary, feedback_count, updated_at)
           VALUES (1, ?, ?, ?)""",
        (summary, feedback_count, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
