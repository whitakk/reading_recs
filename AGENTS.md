# AGENTS.md

Guidance for coding agents working in this repository.

## Project Overview

`reading_recs` is a personal RSS recommendation pipeline. It fetches articles from `feeds.txt`, enriches them with Hacker News and Reddit engagement signals, scores them with OpenAI, stores recommendation history and feedback in SQLite, and sends an HTML email digest through Gmail SMTP.

There is also a Cloudflare Worker in `worker/` that renders the feedback page linked from each digest email and stores thumbs-up/down votes in Cloudflare KV.

## Main Entry Points

- Python pipeline: `python -m reading_recs`
- Package entry: `reading_recs/main.py`
- Feed parsing and article fetching: `reading_recs/fetch.py`
- Popularity enrichment: `reading_recs/popularity.py`
- LLM scoring and selection: `reading_recs/score.py`
- Email rendering/sending: `reading_recs/email_digest.py`
- Feedback sync and KV writes: `reading_recs/feedback.py`
- SQLite schema and helpers: `reading_recs/db.py`
- Cloudflare Worker: `worker/src/index.js`

## Setup

Python requires 3.11 or newer.

```bash
pip install .
```

Runtime secrets are read from `.env` via `python-dotenv`. Required for a real digest run:

```text
OPENAI_API_KEY=
GMAIL_USER=
GMAIL_APP_PASSWORD=
GMAIL_TO=
```

Optional feedback/Worker integration:

```text
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_KV_NAMESPACE_ID=
WORKER_BASE_URL=
```

If Gmail credentials are missing, the pipeline prints the generated digest HTML instead of sending email. If Cloudflare credentials are missing, feedback sync and KV push are skipped.

## Common Commands

Run the digest pipeline:

```bash
python -m reading_recs
```

Install or update Worker dependencies:

```bash
cd worker
npm install
```

Deploy the Cloudflare Worker after changing `worker/src/index.js`:

```bash
cd worker
npx wrangler deploy
```

There is currently no dedicated test suite in the repo. For Python changes, at minimum run import/compile checks and, when safe with available secrets/network, run `python -m reading_recs`.

```bash
python -m compileall reading_recs
```

## Data and State

- `data/reading_recs.db` is a SQLite database used for recommendation deduplication, feed popularity stats, feedback, and preference summaries.
- GitHub Actions updates `data/reading_recs.db` after scheduled digest runs and commits it back to `main`.
- Treat `data/reading_recs.db` as live state. Do not casually replace, delete, reinitialize, or regenerate it.
- Before merging or opening a PR that touches the DB, fetch and merge the latest `main` to avoid overwriting the CI-updated version.
- If a merge conflict occurs on `data/reading_recs.db`, prefer the `main` version unless the user explicitly says otherwise.

## Feeds and Favorites

- `feeds.txt` is user-owned configuration. Preserve comments and grouping when editing.
- Feed lines use `Name | URL` or `Name | URL | N`, where `N` caps entries for that feed.
- `examples/favorites.md` contains high-quality reference articles used in the scoring prompt. The descriptions are more important than the URLs or titles.

## Pipeline Behavior

The current pipeline order is:

1. Initialize SQLite schema.
2. Sync Cloudflare KV feedback into SQLite.
3. Regenerate the preference summary if new feedback exists.
4. Fetch feeds from `feeds.txt`.
5. Exclude URLs already recommended in prior digests.
6. Enrich remaining articles with HN/Reddit popularity.
7. Score articles with `gpt-4o-mini`.
8. Apply source variety penalties.
9. Save scored candidates and recommended URLs to SQLite.
10. Push digest metadata to Cloudflare KV.
11. Send or print the email digest.

Articles below the recommendation threshold are saved with `recommended = 0` for the current run, but deduplication only excludes previously recommended URLs.

## Scoring Notes

- The LLM prompt expects strict JSON: `{"score": <1-10>, "reason": "<2 sentences>"}`.
- Reader-facing reasons should not mention the score or compare article quality.
- `LLM_SCORE_THRESHOLD`, digest size bounds, feed caps, and source penalties live in `reading_recs/config.py`.
- The embedding filter mentioned in older docs is not active in the current code path; candidates are passed directly to LLM scoring.

## Worker Notes

- The Worker expects a KV binding named `FEEDBACK_KV`.
- `wrangler.toml` contains the KV namespace binding.
- Python writes digest records under `digest:{digest_id}`.
- The Worker writes votes under `feedback:{digest_id}:{url_hash}`.
- The Python feedback sync lists KV keys with the `feedback:` prefix and stores them in SQLite.

## Git and Local Changes

- Check the worktree before editing. This repo may contain user edits, especially in `feeds.txt`.
- Do not revert user changes unless explicitly requested.
- In environments that report dubious ownership, use a local command override rather than changing global Git config:

```bash
git -c safe.directory='C:/Users/whita/Documents/My Documents/data_science/80 projects/reading_recs' status --short
```

## Style

- Keep edits small and consistent with the existing straightforward Python style.
- Prefer standard library and existing dependencies over adding new packages.
- Avoid broad refactors unless needed for the requested behavior.
- Use ASCII for new docs/code unless a file already requires non-ASCII.
