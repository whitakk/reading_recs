import hashlib
import json
import logging

import httpx
import openai

from reading_recs import db
from reading_recs.config import (
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_KV_NAMESPACE_ID,
    OPENAI_API_KEY,
)
from reading_recs.models import ScoredArticle

log = logging.getLogger(__name__)

_openai = openai.OpenAI(api_key=OPENAI_API_KEY)


def _kv_headers() -> dict:
    return {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}


def _kv_base_url() -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CLOUDFLARE_KV_NAMESPACE_ID}"


def _cf_configured() -> bool:
    return bool(CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_KV_NAMESPACE_ID)


def push_digest_to_kv(digest_id: str, articles: list[ScoredArticle]):
    """Write digest metadata to Cloudflare KV for the feedback page."""
    if not _cf_configured():
        log.info("Cloudflare not configured — skipping KV push")
        return

    payload = {
        "articles": [
            {
                "url": sa.article.url,
                "url_hash": hashlib.sha256(sa.article.url.encode()).hexdigest()[:16],
                "title": sa.article.title,
                "source": sa.article.source,
                "score": sa.llm_score,
                "reason": sa.reason,
            }
            for sa in articles
        ]
    }

    key = f"digest:{digest_id}"
    url = f"{_kv_base_url()}/values/{key}"
    resp = httpx.put(url, headers=_kv_headers(), content=json.dumps(payload), timeout=30.0)
    if resp.status_code == 200:
        log.info("Pushed digest %s to KV (%d articles)", digest_id, len(articles))
    else:
        log.warning("Failed to push digest to KV: %s %s", resp.status_code, resp.text[:200])


def sync_feedback():
    """Pull feedback from Cloudflare KV into local SQLite."""
    if not _cf_configured():
        log.info("Cloudflare not configured — skipping feedback sync")
        return

    # List all keys with feedback: prefix
    url = f"{_kv_base_url()}/keys"
    resp = httpx.get(url, headers=_kv_headers(), params={"prefix": "feedback:"}, timeout=30.0)
    if resp.status_code != 200:
        log.warning("Failed to list KV keys: %s %s", resp.status_code, resp.text[:200])
        return

    keys = [k["name"] for k in resp.json().get("result", [])]
    if not keys:
        log.info("No feedback entries in KV")
        return

    log.info("Found %d feedback entries in KV", len(keys))
    for key in keys:
        value_url = f"{_kv_base_url()}/values/{key}"
        value_resp = httpx.get(value_url, headers=_kv_headers(), timeout=30.0)
        if value_resp.status_code != 200:
            log.warning("Failed to read KV key %s: %s", key, value_resp.status_code)
            continue

        try:
            data = value_resp.json()
        except json.JSONDecodeError:
            log.warning("Invalid JSON in KV key %s", key)
            continue

        db.save_feedback(
            url=data["url"],
            title=data.get("title", ""),
            source=data.get("source", ""),
            thumbs_up=data.get("thumbs_up", True),
            digest_date=data.get("digest_date", ""),
        )

    log.info("Synced %d feedback entries to SQLite", len(keys))


def ensure_preference_summary():
    """Regenerate preference summary if new feedback exists."""
    current_count = db.get_feedback_count()
    if current_count == 0:
        log.info("No feedback yet — skipping preference summary")
        return

    existing = db.get_preference_summary()
    if existing and existing[1] >= current_count:
        log.info("Preference summary up to date (%d feedback entries)", current_count)
        return

    old_summary = existing[0] if existing else "(none)"

    feedback = db.get_all_feedback()
    liked = [f for f in feedback if f["thumbs_up"]]
    disliked = [f for f in feedback if not f["thumbs_up"]]

    prompt = "Based on the user's article ratings below, write a concise preference profile (1-2 paragraphs) describing what kinds of articles they prefer and dislike. Focus on patterns in topics, writing style, and depth.\n\n"

    if liked:
        prompt += "LIKED:\n"
        for f in liked:
            prompt += f"- {f['title']} ({f['source']})\n"
    if disliked:
        prompt += "\nDISLIKED:\n"
        for f in disliked:
            prompt += f"- {f['title']} ({f['source']})\n"

    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("Failed to generate preference summary: %s", e)
        return

    log.info("Preference summary updated (%d → %d feedback entries)", existing[1] if existing else 0, current_count)
    log.info("  Old: %s", old_summary[:200])
    log.info("  New: %s", summary[:200])

    db.save_preference_summary(summary, current_count)
