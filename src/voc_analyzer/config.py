from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLES_DIR = DATA_DIR / "samples"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


# --- Scraping (Playwright) ---
HEADLESS = _env_bool("VOC_HEADLESS", True)
BROWSER_PROFILE = os.getenv("VOC_BROWSER_PROFILE") or None
SCRAPE_TIMEOUT_MS = _env_int("VOC_SCRAPE_TIMEOUT_MS", 30_000)
MAX_SCROLLS = _env_int("VOC_MAX_SCROLLS", 10)

# --- Agentic gathering loop ---
GATHER_MAX_ROUNDS = _env_int("VOC_GATHER_MAX_ROUNDS", 5)  # hard cap on rounds (cost)
GATHER_TARGET = _env_int("VOC_GATHER_TARGET", 300)  # stop once >= this many unique comments
GATHER_MIN_NEW = _env_int("VOC_GATHER_MIN_NEW", 10)  # diminishing-returns floor per round
GATHER_SAMPLE_SIZE = _env_int("VOC_GATHER_SAMPLE_SIZE", 40)  # comment texts shown to the agent
GATHER_MAX_QUERIES = _env_int("VOC_GATHER_MAX_QUERIES", 6)  # cap on agent queries per round


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def anthropic_enabled() -> bool:
    """True if an Anthropic key is configured (enables LLM-generated suggestions)."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))
