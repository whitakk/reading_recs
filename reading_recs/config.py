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
OPML_PATH = ROOT_DIR / "feeds.opml"
FAVORITES_PATH = ROOT_DIR / "examples" / "favorites.md"

# Pipeline constants
EMBEDDING_TOP_N = 30
LLM_SCORE_THRESHOLD = 7
MIN_ARTICLES = 5
MAX_ARTICLES = 10
