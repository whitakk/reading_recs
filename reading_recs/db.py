import sqlite3
from datetime import date
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

CREATE TABLE IF NOT EXISTS preference_embeddings (
    id INTEGER PRIMARY KEY,
    text TEXT,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS validation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    embedding_score REAL,
    llm_score REAL,
    run_date TEXT
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
                sa.embedding_score,
                sa.llm_score,
                sa.reason,
                1 if sa.article.url in recommended_urls else 0,
                today,
            ),
        )
    conn.commit()
    conn.close()


def save_validation(url: str, embedding_score: float, llm_score: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO validation_log (url, embedding_score, llm_score, run_date) VALUES (?, ?, ?, ?)",
        (url, embedding_score, llm_score, date.today().isoformat()),
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
