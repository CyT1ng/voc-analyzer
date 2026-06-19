from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

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
        log.warning("Ignoring invalid %s=%r; using default %d", name, value, default)
        return default


# --- Scraping (DuckDuckGo search via `ddgs`) ---
DDGS_MAX_RESULTS = _env_int("VOC_DDGS_MAX_RESULTS", 10)  # results per query/platform
DDGS_TIMEOUT_S = _env_int("VOC_DDGS_TIMEOUT_S", 5)  # per-search HTTP timeout (seconds)
DDGS_REGION = os.getenv("VOC_DDGS_REGION", "us-en")  # DuckDuckGo region code
DDGS_BACKEND = os.getenv("VOC_DDGS_BACKEND", "auto")  # ddgs backend selection

# --- Agentic gathering loop ---
# Hard backstops (always terminate the loop): max rounds + max total comments.
GATHER_MAX_ROUNDS = _env_int("VOC_GATHER_MAX_ROUNDS", 5)  # hard cap on rounds (cost)
GATHER_MAX_TOTAL = _env_int("VOC_GATHER_MAX_TOTAL", 1000)  # hard cap on total comments gathered
# Advisory signals shown to the agent (NOT auto-stops — the agent decides):
GATHER_TARGET = _env_int("VOC_GATHER_TARGET", 300)  # rough "enough" target hinted to the agent
GATHER_MIN_NEW = _env_int("VOC_GATHER_MIN_NEW", 10)  # diminishing-returns threshold (signal)
GATHER_MAX_QUERIES = _env_int("VOC_GATHER_MAX_QUERIES", 6)  # cap on agent queries per round

# --- LLM provider (report suggestions/summary + gather agent) ---
# Default backend is Anthropic; set VOC_LLM_PROVIDER=openai to target any OpenAI-compatible
# /chat/completions endpoint (free models such as Qwen via OpenRouter/DashScope/Ollama/vLLM).
# The provider is read live via llm_provider() so dispatch (llm.complete) and gating
# (llm_enabled) can never disagree; only the non-provider settings are cached here.
LLM_BASE_URL = os.getenv("VOC_LLM_BASE_URL") or "https://api.openai.com/v1"
LLM_TIMEOUT_S = _env_int("VOC_LLM_TIMEOUT_S", 60)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def llm_provider() -> str:
    """Selected LLM provider, read live so .env/tests take effect without a module reload."""
    return os.getenv("VOC_LLM_PROVIDER", "anthropic").strip().lower()


def llm_api_key() -> str | None:
    """API key for the selected provider (explicit override → provider default env var)."""
    explicit = os.getenv("VOC_LLM_API_KEY")
    if explicit:
        return explicit
    if llm_provider() == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def llm_enabled() -> bool:
    """True when the selected provider can drive LLM features.

    OpenAI-compatible endpoints don't require a key (e.g. a local Ollama/vLLM server), so
    selecting that provider is enough to attempt them; Anthropic requires a key.
    """
    if llm_provider() == "openai":
        return True
    return bool(llm_api_key())


# Back-compat alias for the pre-provider-abstraction name.
anthropic_enabled = llm_enabled
