# reading_recs

Personal RSS digest pipeline. Fetches feeds → enriches with HN/Reddit popularity → filters via embeddings → scores with LLM → emails a daily digest.

## Running

```bash
python -m reading_recs
```

## Key files

- `feeds.txt` — RSS feed list. Format: `Name | URL` or `Name | URL | N` where N caps entries per feed (useful for undated feeds like Paul Graham).
- `examples/favorites.md` — Articles that calibrate the embedding filter. The 2-sentence descriptions matter most; titles and URLs add little signal.
- `data/reading_recs.db` — SQLite DB tracking recommended articles (for deduplication) and feed popularity stats.

## Key config (`reading_recs/config.py`)

- `FEED_LOOKBACK_DAYS = 7` — skip entries older than this
- `FEED_MAX_ENTRIES = 10` — default per-feed entry cap (fallback for undated feeds)
- `EMBEDDING_TOP_N = 30` — candidates passed to LLM scoring after embedding filter
- `LLM_SCORE_THRESHOLD = 6` — minimum score to include in digest
- `MIN_ARTICLES = 5`, `MAX_ARTICLES = 10` — digest size bounds

## Pipeline stages

1. **fetch** — parse feeds.txt, fetch RSS, deduplicate by URL, fill short entries with full-text scrape
2. **popularity** — query HN Algolia + Reddit for engagement signals; Reddit rate-limits aggressively so the code bails after the first 429
3. **embed** — embed articles + favorites, score by cosine similarity, keep top 30
4. **score** — LLM scores each candidate 1-10 with a reason; articles >= threshold are included
5. **email** — send HTML digest via Gmail SMTP

## Deduplication behavior

The DB only tracks articles that were actually **recommended** (sent in a digest). Articles that get fetched but score below the threshold are not stored, so they can re-appear on future runs. This is intentional for dated feeds (they'll age out) but can cause undated feeds to repeat — use the per-feed entry cap in feeds.txt to limit this.

## .env required keys

```
OPENAI_API_KEY=
GMAIL_USER=
GMAIL_APP_PASSWORD=
GMAIL_TO=
```
