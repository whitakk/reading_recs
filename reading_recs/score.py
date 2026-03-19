import json
import logging
import re

import openai

from reading_recs import db
from reading_recs.config import (
    OPENAI_API_KEY,
    FAVORITES_PATH,
    LLM_SCORE_THRESHOLD,
    MIN_ARTICLES,
    MAX_ARTICLES,
    SOURCE_PENALTY_PER_REC,
    SOURCE_PENALTY_LOOKBACK_DAYS,
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

Respond with ONLY a JSON object: {"score": <1-10>, "reason": "<2 sentences>"}
The reason is a reader-facing blurb — write it the same way regardless of your score. Pull out the most surprising or counterintuitive insight, or summarize the core argument/story. Be direct and specific. Don't start with 'This article' or 'The author'. Never reference the score, quality, depth, or how the piece compares to others. Example: 'Gig economy minimum wages backfire by reducing flexibility — Uber data shows drivers earn less overall after wage floors are set. The real beneficiary turns out to be the platform, not workers.'"""


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


def score_article(
    article_text: str,
    title: str,
    source: str,
    popularity_context: str,
    few_shot: str,
    preference_context: str = "",
) -> dict | None:
    """Score a single article using an LLM."""
    user_msg = f"""Title: {title}
Source: {source}
Popularity: {popularity_context}

Text (excerpt):
{article_text[:3000]}
{few_shot}"""

    if preference_context:
        user_msg += f"\n{preference_context}\n"

    user_msg += "\nScore this article."

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

    # Load preference summary if available
    preference_context = ""
    pref = db.get_preference_summary()
    if pref:
        summary, count = pref
        preference_context = f"\nUser preference profile (based on {count} ratings):\n{summary}\n"
        log.info("Using preference profile (%d ratings)", count)

    for sa in candidates:
        popularity_ctx = (
            f"{'Above' if sa.article.is_above_average else 'Below'} average engagement for {sa.article.source}. "
            f"{sa.article.comment_count} comments."
        )
        if sa.article.limited_data:
            popularity_ctx += " (Limited text data — full article could not be fetched.)"

        result = score_article(
            sa.article.text, sa.article.title, sa.article.source, popularity_ctx, few_shot, preference_context,
        )
        if result:
            sa.llm_score = result["score"]
            sa.reason = result["reason"]
            log.info("  %s — score: %d, reason: %s", sa.article.title[:50], sa.llm_score, sa.reason)

    # Apply source variety penalty based on recent recommendation history
    source_counts = db.get_recent_source_counts(SOURCE_PENALTY_LOOKBACK_DAYS)
    for sa in candidates:
        count = source_counts.get(sa.article.source, 0)
        penalty = SOURCE_PENALTY_PER_REC * count
        sa.adjusted_score = sa.llm_score - penalty
        if penalty > 0:
            log.info("  %s — penalty %.1f (source '%s' recommended %d times in last %d days)",
                     sa.article.title[:50], penalty, sa.article.source, count, SOURCE_PENALTY_LOOKBACK_DAYS)

    # Select: adjusted_score >= threshold, floor at MIN, cap at MAX
    passing = [sa for sa in candidates if sa.adjusted_score >= LLM_SCORE_THRESHOLD]
    passing.sort(key=lambda s: s.adjusted_score, reverse=True)

    if len(passing) < MIN_ARTICLES:
        # Fall back to top by adjusted score
        all_scored = [sa for sa in candidates if sa.llm_score > 0]
        all_scored.sort(key=lambda s: s.adjusted_score, reverse=True)
        passing = all_scored[:MIN_ARTICLES]

    selected = passing[:MAX_ARTICLES]
    return selected
