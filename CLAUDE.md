# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Voice-of-Customer analyzer: given an e-commerce product, scrape user comments from
YouTube / Reddit / TikTok / Instagram / X, unify them into one schema, run local NLP
(sentiment / keywords / trends), and emit a Markdown + JSON insight report with
improvement suggestions. Single CLI command drives the whole pipeline.

## Commands

```bash
uv sync                       # runtime deps
uv sync --extra dev           # + pytest, pytest-cov, ruff
uv sync --extra llm           # + anthropic (only needed for LLM suggestions)
uv run playwright install chromium   # one-time, required before ANY live scrape

uv run ruff check .           # lint (add --fix to autofix)
uv run pytest                 # unit tests — OFFLINE, no browser/network (integration deselected by default)
uv run pytest tests/test_analyze.py::test_sentiment_labels   # single test
uv run pytest -k keyword      # tests matching a substring
uv run pytest -m integration  # opt-in live tests — the marker is registered but UNUSED today (suite is fully offline)

# Run the pipeline
uv run voc-analyzer run -p "Sony WH-1000XM5" -k "noise cancelling" -P youtube --limit 60
uv run voc-analyzer run -p "Acme Buds" --from-raw data/samples/comments.jsonl   # offline demo, no scraping
uv run voc-analyzer run ... --no-llm        # force rule-based suggestions
```

Reports are written to `data/processed/report.md` + `analysis.json` (override with `--output-dir`).
`pytest` deselects `integration`-marked tests via `addopts` in `pyproject.toml`; CI runs the plain
`uv run pytest` (offline) — so **never assume the browser/network is available in a test**.

## Architecture

Linear pipeline, one package subfolder per stage. Data flows:
`search → scrape → integrate → analyze → report`, orchestrated in `cli.py::run`.

- **`integrate/schema.py::Comment`** is the contract for the whole system. Every scraper
  produces `Comment`s; everything downstream consumes them. Change it deliberately.
- **`search/`** — `build(product, keywords, platforms)` turns the product + keywords into a
  per-platform dict of query strings. The bare product name is always one of the queries.
- **`scrape/<platform>.py`** — each scraper splits a **pure `parse(html) -> list[Comment]`**
  from a **live `fetch(query, limit)`**. `parse()` is unit-tested offline against fixtures in
  `data/samples/`; `fetch()` drives the browser and, on any failure, **catches `ScrapeError`
  and returns `[]`** (best-effort — a scrape returning nothing is normal, not a crash).
  - `scrape/_browser.py::Browser` is the shared Playwright wrapper (context manager).
    `render(url, wait_selector)` returns HTML after auto-scrolling lazy feeds; `get_json(url)`
    fetches via the browser's request context (used by Reddit). Playwright is imported lazily so
    the package and the offline parse-tests need no browser installed.
  - **Reddit is special**: it parses the public `.json` API (`search.json` / `{permalink}.json`)
    via `Browser.get_json`, not HTML — `parse_comments` / `post_permalinks` walk JSON.
- **`integrate/pipeline.py::integrate`** flattens per-platform batches and `clean`s them:
  NFKC-normalize text → drop <3-char noise → dedupe by native `(source, source_id)` →
  collapse near-duplicate reposts (same source + same alphanumeric-stripped text). Order matters.
- **`analyze/__init__.py::build_analysis`** is the public analysis entry point: it returns the
  single `analysis` dict (sentiment via VADER, keywords/phrases, keywords-by-sentiment, trends,
  representative quotes) that the report renders and `analysis.json` is dumped from.
- **`report/`** — `render.write_report(analysis, out_dir) -> (md_path, json_path)`;
  `suggest.suggest(analysis, use_llm)` returns improvement suggestions, **rule-based by default**,
  switching to Claude only when `ANTHROPIC_API_KEY` is set, with graceful fallback to rule-based
  on any LLM error.

### Cross-file invariant

The set of platforms is hard-coded in **three** places that must stay in sync:
`schema.py::Source` (the `Literal`), `search/__init__.py::PLATFORMS`, and `cli.py::FETCHERS`.
Adding a platform = new `scrape/<platform>.py` with `parse`+`fetch`, plus an entry in all three.

## Platform reliability (see `docs/platforms.md`)

- **YouTube** — no login, reliable. The out-of-the-box path.
- **Reddit** — login-free `.json` API, but **rate-limited by IP**: datacenter/CI/sandbox IPs get
  HTTP 403 on every endpoint; residential IPs generally work. Returns `[]` (with a warning) when blocked.
- **TikTok / Instagram / X** — login-walled + anti-bot, **best-effort**. They only return data when
  `VOC_BROWSER_PROFILE` points at a Chromium profile already signed in (usually with `VOC_HEADLESS=false`).
  Selectors target the current public DOM and drift as the sites change — when one breaks, the fix
  lives in that platform's `parse()` and its fixture, testable without a browser.

`scripts/smoke_xig.py "<query>"` is an interactive headed harness to log into X/IG once and capture
their live HTML into `.scratch/` for parser work.

## Config (env vars, read in `config.py`)

`VOC_HEADLESS` (default true) · `VOC_BROWSER_PROFILE` · `VOC_SCRAPE_TIMEOUT_MS` (30000) ·
`VOC_MAX_SCROLLS` (10) · `ANTHROPIC_API_KEY` (enables LLM suggestions) ·
`VOC_LLM_MODEL` (default `claude-opus-4-8`) · `DATA_DIR`. Loaded from `.env` (see `.env.example`).

## Conventions

- Ruff: line length 100, rules `E,F,I,B,UP,SIM`, target py311. `from __future__ import annotations` everywhere.
- Tests mirror `src/` structure under `tests/`. Keep parser logic pure so it stays browser-free testable.
- Scrapers degrade, never abort: `cli.py::_scrape` also wraps each fetch in try/except so one failing
  platform/query can't take down the run.
