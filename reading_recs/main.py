import logging
import uuid

from reading_recs import db
from reading_recs.config import WORKER_BASE_URL
from reading_recs.fetch import fetch_all
from reading_recs.popularity import enrich
from reading_recs.feedback import push_digest_to_kv, sync_feedback, ensure_preference_summary
from reading_recs.score import score_and_select
from reading_recs.email_digest import build_and_send
from reading_recs.models import ScoredArticle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def run():
    log.info("Initializing database")
    db.init_db()

    log.info("Syncing feedback from Cloudflare KV")
    sync_feedback()
    ensure_preference_summary()

    log.info("Fetching articles from feeds")
    articles = fetch_all()
    log.info("Fetched %d articles", len(articles))

    previously_recommended = db.get_previously_recommended()
    articles = [a for a in articles if a.url not in previously_recommended]
    log.info("%d new articles after excluding previously recommended", len(articles))

    if not articles:
        log.info("No new articles, sending empty digest")
        build_and_send([])
        return

    log.info("Enriching with popularity signals")
    articles = enrich(articles)

    # Convert articles directly to ScoredArticle list (no embedding filter)
    candidates = [ScoredArticle(article=a) for a in articles]

    log.info("Running LLM scoring on %d articles", len(candidates))
    selected = score_and_select(candidates)
    log.info("Selected %d articles for digest", len(selected))

    recommended_urls = {sa.article.url for sa in selected}
    db.save_articles(candidates, recommended_urls)

    # Push digest to KV for feedback page
    digest_id = uuid.uuid4().hex
    push_digest_to_kv(digest_id, selected)

    feedback_url = ""
    if WORKER_BASE_URL:
        feedback_url = f"{WORKER_BASE_URL.rstrip('/')}/feedback/{digest_id}"

    log.info("Sending email digest")
    build_and_send(selected, feedback_url)
    log.info("Done")


if __name__ == "__main__":
    run()
