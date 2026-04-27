from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# API keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Email
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_TO = os.environ.get("GMAIL_TO", "")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "reading_recs.db"
FEEDS_PATH = ROOT_DIR / "feeds.txt"
FAVORITES_PATH = ROOT_DIR / "examples" / "favorites.md"

# Pipeline constants
FEED_LOOKBACK_DAYS = 7
FEED_MAX_ENTRIES = 10  # per feed, as fallback for undated feeds
LLM_SCORE_THRESHOLD = 6
MIN_ARTICLES = 5
MAX_ARTICLES = 10
TOP_SOURCE_BOOST = 2.0
SOURCE_PENALTY_PER_REC = 0.3    # score penalty per recent recommendation from the same source
SOURCE_PENALTY_LOOKBACK_DAYS = 14  # window for counting recent recommendations

# Cloudflare (feedback system)
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_KV_NAMESPACE_ID = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID", "")
WORKER_BASE_URL = os.environ.get("WORKER_BASE_URL", "")
