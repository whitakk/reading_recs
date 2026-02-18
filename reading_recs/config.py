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
EMBEDDING_TOP_N = 30
LLM_SCORE_THRESHOLD = 7
MIN_ARTICLES = 5
MAX_ARTICLES = 10
