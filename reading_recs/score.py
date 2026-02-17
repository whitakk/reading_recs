import json
import logging
import random
import re

import openai

from reading_recs import db
from reading_recs.config import (
    OPENAI_API_KEY,
    FAVORITES_PATH,
    LLM_SCORE_THRESHOLD,
    MIN_ARTICLES,
    MAX_ARTICLES,
)
from reading_recs.models import ScoredArticle

log = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a reading recommendation scorer. Given an article's title, source, text excerpt, and popularity context, score it from 1-10 on how worth reading it is.

Criteria:
- Opinionated — not just factual news
- Info-dense — packed with insights, not padded
- Differentiated — unique perspective, not a generic take
- Topically biased toward (but not limited to): economics, AI, data science, technology, business strategy, public policy

Respond with ONLY a JSON object: {"score": <1-10>, "reason": "<1-2 sentences summarizing what makes it interesting>"}
The reason should tell the reader what they'll get from the article. Be direct — don't start with 'This article' or 'The author'. Example: 'Argues that gig economy minimum wages backfire by reducing flexibility, with strong evidence from recent Uber data.'"""


def _load_few_shot_examples() -> str:
    if not FAVORITES_PATH.exists():
        return ""
    content = FAVORITES_PATH.read_text()
    return f"\nHere are examples of articles the user considers high quality (score 9-10):\n\n{content}\n"


def _parse_llm_response(text: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    # Strip markdown code blocks
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        result = json.loads(text)
        if "score" in result and "reason" in result:
            return result
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM response: %s", text[:200])
    return None


def score_article(article_text: str, title: str, source: str, popularity_context: str, few_shot: str) -> dict | None:
    """Score a single article using an LLM."""
    user_msg = f"""Title: {title}
Source: {source}
Popularity: {popularity_context}

Text (excerpt):
{article_text[:3000]}
{few_shot}
Score this article."""

    try:
        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return _parse_llm_response(resp.choices[0].message.content)
    except Exception as e:
        log.warning("LLM scoring failed for %s: %s", title, e)
        return None


def score_and_select(candidates: list[ScoredArticle]) -> list[ScoredArticle]:
    """Score candidates with LLM, select top articles for digest."""
    few_shot = _load_few_shot_examples()

    for sa in candidates:
        popularity_ctx = (
            f"{'Above' if sa.article.is_above_average else 'Below'} average engagement for {sa.article.source}. "
            f"{sa.article.comment_count} comments."
        )
        if sa.article.limited_data:
            popularity_ctx += " (Limited text data — full article could not be fetched.)"

        result = score_article(
            sa.article.text, sa.article.title, sa.article.source, popularity_ctx, few_shot,
        )
        if result:
            sa.llm_score = result["score"]
            sa.reason = result["reason"]
            log.info("  %s — score: %d, reason: %s", sa.article.title[:50], sa.llm_score, sa.reason)

    # Validation: every 7th run, also score 5 random embedding-rejected articles
    _maybe_run_validation(candidates)

    # Select: score >= threshold, floor at MIN, cap at MAX
    passing = [sa for sa in candidates if sa.llm_score >= LLM_SCORE_THRESHOLD]
    passing.sort(key=lambda s: s.llm_score, reverse=True)

    if len(passing) < MIN_ARTICLES:
        # Fall back to top by LLM score
        all_scored = [sa for sa in candidates if sa.llm_score > 0]
        all_scored.sort(key=lambda s: s.llm_score, reverse=True)
        passing = all_scored[:MIN_ARTICLES]

    selected = passing[:MAX_ARTICLES]
    return selected


def _maybe_run_validation(candidates: list[ScoredArticle]):
    """Every 7th run, LLM-score some embedding-rejected articles for calibration."""
    conn = db.get_conn()
    run_count = conn.execute("SELECT COUNT(DISTINCT run_date) FROM articles").fetchone()[0]
    conn.close()

    if run_count % 7 != 0:
        return

    # Pick 5 from the bottom half of embedding scores
    bottom = sorted(candidates, key=lambda s: s.embedding_score)[:len(candidates) // 2]
    sample = random.sample(bottom, min(5, len(bottom)))
    few_shot = _load_few_shot_examples()

    log.info("Running validation on %d embedding-rejected articles", len(sample))
    for sa in sample:
        result = score_article(sa.article.text, sa.article.title, sa.article.source, "", few_shot)
        if result:
            db.save_validation(sa.article.url, sa.embedding_score, result["score"])
            log.info("  Validation: %s — embed=%.3f, llm=%d", sa.article.title[:40], sa.embedding_score, result["score"])
