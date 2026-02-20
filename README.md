# reading_recs

A personal RSS digest pipeline that emails you a daily set of recommended articles. It fetches from a curated list of feeds, enriches articles with HN/Reddit popularity signals, filters candidates by similarity to your saved favorites, scores them with an LLM, and sends an HTML email digest.

## Setup

1. Copy `.env.example` to `.env` and fill in your keys:

```
OPENAI_API_KEY=
GMAIL_USER=
GMAIL_APP_PASSWORD=
GMAIL_TO=
```

2. Install dependencies (Python 3.11+):

```bash
pip install -r requirements.txt
```

## Running

```bash
python -m reading_recs
```

To run on a schedule, a GitHub Actions workflow is included at `.github/workflows/digest.yml`. It runs weekdays at 8am ET. Add your `.env` values as repository secrets under **Settings → Secrets and variables → Actions**, then push to GitHub. You can also trigger it manually from the **Actions** tab.

## Customizing

### Feeds (`feeds.txt`)

Each line is a feed in the format `Name | URL`. You can optionally cap how many entries are pulled per run by appending a count:

```
Name | URL
Name | URL | 3   # only pull 3 entries max (useful for undated feeds)
```

Lines starting with `#` are comments and can be used to group feeds. Remove or add lines to change what sources are considered.

### Favorites (`examples/favorites.md`)

This file teaches the system what kinds of articles you like. It's used to filter candidates before LLM scoring — articles that are dissimilar to your favorites get dropped early.

Each entry is a heading (title), URL, and a 2-sentence description of what makes it valuable. The **descriptions matter most**; titles and URLs add little signal. Focus on voice, depth, and what's distinctive about each piece.

To add a favorite:

```markdown
## Article Title
https://example.com/article

One sentence on what makes it distinctive. A second sentence on the voice or lens it uses.
```

The more varied and representative your favorites are, the better the filter works.

### Config (`reading_recs/config.py`)

Key settings you might want to tune:

| Setting | Default | Description |
|---|---|---|
| `FEED_LOOKBACK_DAYS` | 7 | Skip entries older than this many days |
| `FEED_MAX_ENTRIES` | 10 | Default per-feed entry cap (fallback when no date is available) |
| `EMBEDDING_TOP_N` | 30 | How many candidates to pass to LLM scoring after the embedding filter |
| `LLM_SCORE_THRESHOLD` | 6 | Minimum score (1–10) to include in the digest |
| `MIN_ARTICLES` | 5 | Minimum digest size |
| `MAX_ARTICLES` | 10 | Maximum digest size |
