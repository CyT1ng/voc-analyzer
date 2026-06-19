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

- **Scrape** uses **DuckDuckGo search** (the keyless `ddgs` library) — no browser,
  no login, no API keys. Each platform runs a `site:<domain>` search. Results are
  search-result *snippets*, not full comment threads, so the analysis is
  directional (no author/likes, scrape-time timestamps); see `docs/platforms.md`.
  Every fetch is best-effort and degrades gracefully.
- **Analyze** is local NLP: [VADER](https://github.com/cjhutto/vaderSentiment)
  sentiment, frequency-based keywords, and day-bucketed trends.
- **Insight** is a Markdown report + `analysis.json`. Improvement suggestions are
  rule-based by default, or LLM-generated if an LLM provider is configured (Anthropic
  by default, or any free OpenAI-compatible model — see below).

## Quick start

```bash
# 1. Install uv (https://docs.astral.sh/uv/) if you don't have it
# 2. Sync dependencies (pulls `ddgs`; no browser to install)
uv sync

# 3. (optional) Copy env template for scraping/LLM settings
cp .env.example .env

# 4a. Live run — all platforms via DuckDuckGo search (keyless, browser-free)
uv run voc-analyzer run -p "Sony WH-1000XM5" -k "noise cancelling"

# 4b. Just one platform, single pass
uv run voc-analyzer run -p "Sony WH-1000XM5" -P reddit --max-rounds 1

# 4c. Offline demo — analyze the committed sample comments
uv run voc-analyzer run -p "Acme Buds" --from-raw data/samples/comments.jsonl
```

Output is written to `data/processed/report.md` and `data/processed/analysis.json`
(override with `--output-dir`). Add `--no-llm` to force rule-based suggestions.

### LLM features are optional

The executive summary, improvement suggestions, and the gather agent are LLM-powered,
but **the tool runs with no LLM at all** — suggestions fall back to a deterministic
rule-based path and the summary is simply omitted. So you need no account to use it.
To enable the LLM features, configure a provider (all route through one
provider-agnostic call, so any OpenAI-compatible endpoint works).

#### Qwen via OpenRouter (recommended — hosted, strong model)

1. Create an API key at <https://openrouter.ai/keys>.
2. Run (or put these in `.env`):

```bash
VOC_LLM_PROVIDER=openai \
VOC_LLM_BASE_URL=https://openrouter.ai/api/v1 \
VOC_LLM_API_KEY=sk-or-...   # your OpenRouter key \
VOC_LLM_MODEL=qwen/qwen3-next-80b-a3b-instruct \
VOC_AGENT_MODEL=qwen/qwen3-next-80b-a3b-instruct \
    uv run voc-analyzer run -p "Sony WH-1000XM5" -P reddit --max-rounds 1
```

Notes:
- Use an **instruct** model id. Reasoning models (Qwen3 thinking, DeepSeek-R1) can return
  empty `content` on some OpenAI-compatible servers and silently fall back to rule-based.
- The `:free` model variants are heavily rate-limited (they 429 on a multi-call run even
  with credit). A small one-time OpenRouter credit unlocks the **paid** id above, which is
  cheap — a full report run is well under a cent. Model ids drift; check
  <https://openrouter.ai/models?q=qwen>.

#### Fully local & keyless via Ollama (private, no key)

```bash
ollama pull qwen2.5            # one-time
VOC_LLM_PROVIDER=openai \
VOC_LLM_BASE_URL=http://localhost:11434/v1 \
VOC_LLM_MODEL=qwen2.5 VOC_AGENT_MODEL=qwen2.5 \
    uv run voc-analyzer run -p "Sony WH-1000XM5" -P reddit --max-rounds 1
```

No API key needed for a local server. Quality is bounded by the model your hardware can run.

#### Anthropic (default)

Set `ANTHROPIC_API_KEY` and `uv sync --extra llm`; leave `VOC_LLM_PROVIDER` unset.

## Layout

```
src/voc_analyzer/   # main package, one folder per pipeline stage
docs/               # design docs and per-platform notes
tests/              # mirrors src/ structure
data/samples/       # tiny committed sample data + DDGS fixture
data/raw/           # scraped data (gitignored)
data/processed/     # reports (gitignored)
notebooks/          # exploration
scripts/            # one-off helpers
```

## Development

```bash
uv sync --extra dev          # dev tooling (pytest, ruff)
uv run ruff check .          # lint
uv run pytest                # unit tests (offline, no network)
uv run pytest -m integration # live tests (hit DDGS / LLM APIs)
```

## Status

Pipeline implemented end-to-end (scrape → analyze → report). See
[docs/0001-architecture.md](docs/0001-architecture.md).
