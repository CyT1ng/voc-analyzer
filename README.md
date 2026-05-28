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

## Quick start

```bash
# 1. Install uv (https://docs.astral.sh/uv/) if you don't have it
# 2. Sync dependencies
uv sync

# 3. Copy env template and fill in API keys
cp .env.example .env

# 4. Run the CLI (placeholder for now)
uv run voc-analyzer --help
```

## Layout

```
src/voc_analyzer/   # main package, one folder per pipeline stage
docs/               # design docs and per-platform notes
tests/              # mirrors src/ structure
data/samples/       # tiny committed sample data
data/raw/           # scraped data (gitignored)
data/processed/     # cleaned data (gitignored)
notebooks/          # exploration
scripts/            # one-off helpers
```

## Status

W1 — kickoff, repo skeleton. See [docs/0001-architecture.md](docs/0001-architecture.md).
