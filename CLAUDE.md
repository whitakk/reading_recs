# reading_recs

Personal RSS digest pipeline. Fetches feeds → enriches with HN/Reddit popularity → scores with LLM → emails a daily digest with feedback links.

## Running

```bash
python -m reading_recs
```

## Key files

- `feeds.txt` — RSS feed list. Format: `Name | URL` or `Name | URL | N` where N caps entries per feed (useful for undated feeds like Paul Graham).
- `examples/favorites.md` — Articles used as few-shot examples in the LLM scoring prompt (high-quality reference articles).
- `data/reading_recs.db` — SQLite DB tracking recommended articles (for deduplication), feed popularity stats, feedback, and preference summary.
- `worker/` — Cloudflare Worker that serves the feedback page and stores votes in KV.

## Key config (`reading_recs/config.py`)

- `FEED_LOOKBACK_DAYS = 7` — skip entries older than this
- `FEED_MAX_ENTRIES = 10` — default per-feed entry cap (fallback for undated feeds)
- `LLM_SCORE_THRESHOLD = 6` — minimum score to include in digest
- `MIN_ARTICLES = 5`, `MAX_ARTICLES = 10` — digest size bounds

## Pipeline stages

1. **feedback sync** — pull thumbs-up/down votes from Cloudflare KV into SQLite; regenerate preference summary if new feedback exists
2. **fetch** — parse feeds.txt, fetch RSS, deduplicate by URL, fill short entries with full-text scrape
3. **popularity** — query HN Algolia + Reddit for engagement signals; Reddit rate-limits aggressively so the code bails after the first 429
4. **score** — LLM scores each candidate 1-10 with a reason (preference summary injected into prompt); articles >= threshold are included
5. **email** — send HTML digest via Gmail SMTP with feedback link

## Feedback system

Each digest email includes a "Rate these recommendations" link pointing to a Cloudflare Worker. Users can thumbs-up/down articles. On the next pipeline run, feedback is synced from KV to SQLite, and GPT-4o-mini generates a preference summary that gets injected into the scoring prompt.

## Deduplication behavior

The DB only tracks articles that were actually **recommended** (sent in a digest). Articles that get fetched but score below the threshold are not stored, so they can re-appear on future runs. This is intentional for dated feeds (they'll age out) but can cause undated feeds to repeat — use the per-feed entry cap in feeds.txt to limit this.

## Before merging a branch or creating a PR

`data/reading_recs.db` is updated daily by GitHub Actions. Always fetch and merge the latest `main` before merging or opening a PR to avoid overwriting the DB with a stale version:

```bash
git fetch origin && git merge origin/main
```

## .env required keys

```
OPENAI_API_KEY=
GMAIL_USER=
GMAIL_APP_PASSWORD=
GMAIL_TO=
```

## .env optional keys (feedback system)

```
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_KV_NAMESPACE_ID=
WORKER_BASE_URL=
```
