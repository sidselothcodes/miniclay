"""Shared configuration for the MiniClay enrichment backend."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_SELLER_CONTEXT = (
    "We build an automated LLM evaluation and observability engine that catches "
    "hallucinations, retrieval regressions, and latency spikes in production AI workflows."
)
DEFAULT_DOMAINS = ["stripe.com", "notion.so", "vercel.com", "linear.app", "ramp.com"]

MAX_DOMAINS = 25
MAX_SELLER_CONTEXT_CHARS = 600
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "5"))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Optional: raises GitHub's API rate limit from 60 to 5,000 requests/hour.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None

# Timeouts (seconds). Every source has its own budget so one slow page never stalls a row.
PAGE_TIMEOUT = float(os.getenv("PAGE_TIMEOUT", "8"))
SEARCH_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "12"))
DNS_TIMEOUT = float(os.getenv("DNS_TIMEOUT", "4"))
SOURCE_TIMEOUT = float(os.getenv("SOURCE_TIMEOUT", "20"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "40"))

CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", "168"))
DB_PATH = os.getenv("MINICLAY_DB", str(BASE_DIR / "miniclay.db"))
SEED_PATH = BASE_DIR / "data" / "seed_results.json"

# Source labels shown as badges in the UI. "AI" is intentionally not a source.
SOURCE_WEBSITE = "Website"
SOURCE_PRICING = "Pricing"
SOURCE_GITHUB = "GitHub"
SOURCE_NEWS = "News"
SOURCE_LINKEDIN = "LinkedIn"
ALL_SOURCES = [SOURCE_WEBSITE, SOURCE_PRICING, SOURCE_GITHUB, SOURCE_NEWS, SOURCE_LINKEDIN]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
