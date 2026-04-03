"""Clawbot configuration — all settings in one place."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- ICPSR credentials ---
EMAIL_LOGIN = os.getenv("EMAIL_LOGIN", "")
PASSWORD = os.getenv("PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Paths ---
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "download_staging"
SESSION_FILE = BASE_DIR / "session.json"
TRACKER_CSV = BASE_DIR / "project_log.csv"
TRACKER_JSON = BASE_DIR / "download_tracker.json"

# --- Search ---
SEARCH_URL = "https://www.openicpsr.org/openicpsr/search/aea/studies"
SEARCH_SORT = "DATEUPDATED%20desc"
ROWS_PER_PAGE = 25
MAX_PAGES = 500

# --- Targets ---
TARGET_COUNT = 100
TARGET_YEARS = None  # Set to e.g. {"2021", "2022"} to filter, or None for all

# --- Politeness ---
MIN_DELAY = 30
MAX_DELAY = 60

# --- Browser ---
CDP_URL = "http://127.0.0.1:9222"  # Chrome remote debugging port

# --- LLM ---
LLM_MODEL = "claude-sonnet-4-6"

# --- CSV fields ---
CSV_FIELDS = [
    "project_id", "title", "checked_at", "has_readme", "readme_type",
    "classification", "rationale", "downloaded", "download_size_mb",
    "error", "notes",
]
