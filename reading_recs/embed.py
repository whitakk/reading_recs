import hashlib
import logging
import struct

from openai import OpenAI

from reading_recs import db
from reading_recs.config import OPENAI_API_KEY, FAVORITES_PATH, EMBEDDING_TOP_N
from reading_recs.models import Article, ScoredArticle

log = logging.getLogger(__name__)

_openai = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "text-embedding-3-small"
DIMS = 1536


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using OpenAI API."""
    # Truncate texts to avoid token limits
    truncated = [t[:8000] for t in texts]
    resp = _openai.embeddings.create(input=truncated, model=MODEL)
    return [d.embedding for d in resp.data]


def _embedding_to_blob(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def _blob_to_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _parse_favorites() -> list[str]:
    """Parse favorites.md into individual example texts."""
    if not FAVORITES_PATH.exists():
        log.warning("No favorites.md found at %s", FAVORITES_PATH)
        return []
    content = FAVORITES_PATH.read_text()
    # Split on markdown headers or double newlines to get individual entries
    entries = []
    current = []
    for line in content.split("\n"):
        if line.startswith("## ") and current:
            entries.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append("\n".join(current).strip())
    return [e for e in entries if len(e) > 20]


def load_preference_profile() -> list[list[float]]:
    """Load or compute preference embeddings from favorites.md."""
    favorites = _parse_favorites()
    if not favorites:
        log.warning("No favorites found — embedding pass will be ineffective")
        return []

    # Check cache: hash the favorites content to detect changes
    content_hash = hashlib.md5("\n".join(favorites).encode()).hexdigest()

    conn = db.get_conn()
    cached = conn.execute("SELECT text, embedding FROM preference_embeddings").fetchall()
    conn.close()

    if cached:
        cached_hash = hashlib.md5("\n".join(r[0] for r in cached).encode()).hexdigest()
        if cached_hash == content_hash:
            log.info("Using cached preference embeddings (%d entries)", len(cached))
            return [_blob_to_embedding(r[1]) for r in cached]

    # Recompute
    log.info("Computing preference embeddings for %d favorites", len(favorites))
    embeddings = _embed_texts(favorites)

    conn = db.get_conn()
    conn.execute("DELETE FROM preference_embeddings")
    for text, emb in zip(favorites, embeddings):
        conn.execute(
            "INSERT INTO preference_embeddings (text, embedding) VALUES (?, ?)",
            (text, _embedding_to_blob(emb)),
        )
    conn.commit()
    conn.close()

    return embeddings


def score_against_profile(embedding: list[float], profile: list[list[float]]) -> float:
    """Average cosine similarity against all preference embeddings."""
    if not profile:
        return 0.0
    return sum(_cosine_similarity(embedding, p) for p in profile) / len(profile)


def filter_top(articles: list[Article], n: int = EMBEDDING_TOP_N) -> list[ScoredArticle]:
    """Embed articles, score against preference profile, return top N."""
    if not articles:
        return []

    profile = load_preference_profile()

    # Embed all articles (title + text snippet)
    texts = [f"{a.title}\n\n{a.text[:2000]}" for a in articles]
    log.info("Embedding %d articles", len(texts))
    embeddings = _embed_texts(texts)

    scored = []
    for article, emb in zip(articles, embeddings):
        sim = score_against_profile(emb, profile)
        scored.append(ScoredArticle(article=article, embedding_score=sim))

    scored.sort(key=lambda s: s.embedding_score, reverse=True)

    top = scored[:n]
    log.info(
        "Embedding scores: top=%.3f, cutoff=%.3f, bottom=%.3f",
        scored[0].embedding_score if scored else 0,
        top[-1].embedding_score if top else 0,
        scored[-1].embedding_score if scored else 0,
    )
    return top
