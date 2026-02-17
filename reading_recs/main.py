import logging

from reading_recs import db
from reading_recs.fetch import fetch_all
from reading_recs.popularity import enrich
from reading_recs.embed import filter_top
from reading_recs.score import score_and_select
from reading_recs.email_digest import build_and_send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def run():
    log.info("Initializing database")
    db.init_db()

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

    log.info("Running embedding pass")
    candidates = filter_top(articles)
    log.info("Embedding pass selected %d candidates", len(candidates))

    log.info("Running LLM scoring")
    selected = score_and_select(candidates)
    log.info("Selected %d articles for digest", len(selected))

    recommended_urls = {sa.article.url for sa in selected}
    db.save_articles(candidates, recommended_urls)

    log.info("Sending email digest")
    build_and_send(selected)
    log.info("Done")


if __name__ == "__main__":
    run()
