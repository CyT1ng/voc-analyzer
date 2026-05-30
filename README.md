# VoC Analyzer

Voice-of-Customer analyzer for overseas social platforms. Given a target
e-commerce product, scrape user voices from YouTube, TikTok, Reddit,
Instagram, and X; clean and integrate them; analyze sentiment, keywords,
and trends; output an insight report with product-improvement suggestions.

## Pipeline

```
Input  ─►  Search  ─►  Scrape  ─►  Integrate  ─►  Analyze  ─►  Insight
(product) (keywords) (per platform) (clean+unify) (NLP/LLM)  (report)
```

- **Scrape** uses **Playwright** (a headless browser) against public pages — no
  platform API keys required. YouTube works out of the box; Reddit uses its
  public `.json` API but is rate-limited by IP (often 403 from datacenter/CI
  IPs, fine from residential); TikTok / Instagram / X are login-walled. All are
  best-effort and degrade gracefully (see `docs/platforms.md`).
- **Analyze** is local NLP: [VADER](https://github.com/cjhutto/vaderSentiment)
  sentiment, frequency-based keywords, and day-bucketed trends.
- **Insight** is a Markdown report + `analysis.json`. Improvement suggestions are
  rule-based by default, or LLM-generated if an `ANTHROPIC_API_KEY` is set.

## Quick start

```bash
# 1. Install uv (https://docs.astral.sh/uv/) if you don't have it
# 2. Sync dependencies
uv sync

# 3. Install the Chromium browser used for scraping (one-time)
uv run playwright install chromium

# 4. (optional) Copy env template for runtime/LLM settings
cp .env.example .env

# 5a. Live run — scrape YouTube (most reliable path) for a product
uv run voc-analyzer run -p "Sony WH-1000XM5" -k "noise cancelling" \
    -P youtube --limit 60

# 5b. Offline demo — analyze the committed sample comments
uv run voc-analyzer run -p "Acme Buds" --from-raw data/samples/comments.jsonl
```

Output is written to `data/processed/report.md` and `data/processed/analysis.json`
(override with `--output-dir`). Add `--no-llm` to force rule-based suggestions.

### Scraping login-walled platforms

TikTok, Instagram, and X gate content behind login/anti-bot. Point
`VOC_BROWSER_PROFILE` at a Chromium profile already logged in to those sites:

```bash
VOC_HEADLESS=false VOC_BROWSER_PROFILE=~/.voc-profile \
    uv run voc-analyzer run -p "Acme Buds" -P tiktok -P instagram -P x
```

## Layout

```
src/voc_analyzer/   # main package, one folder per pipeline stage
docs/               # design docs and per-platform notes
tests/              # mirrors src/ structure
data/samples/       # tiny committed sample data + HTML fixtures
data/raw/           # scraped data (gitignored)
data/processed/     # reports (gitignored)
notebooks/          # exploration
scripts/            # one-off helpers
```

## Development

```bash
uv sync --extra dev          # dev tooling (pytest, ruff)
uv run ruff check .          # lint
uv run pytest                # unit tests (offline, no browser/network)
uv run pytest -m integration # live scraper smoke tests (needs browser + network)
```

## Status

Pipeline implemented end-to-end (scrape → analyze → report). See
[docs/0001-architecture.md](docs/0001-architecture.md).
