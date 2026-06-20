# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Voice-of-Customer analyzer: given an e-commerce product, scrape user comments from
YouTube / Reddit / TikTok / Instagram / X, unify them into one schema, run local NLP
(sentiment / keywords / trends), and emit a Markdown + JSON insight report with
improvement suggestions. Single CLI command drives the whole pipeline.

## Commands

```bash
uv sync                       # runtime deps (includes `ddgs`; no browser to install)
uv sync --extra dev           # + pytest, pytest-cov, ruff
uv sync --extra llm           # + anthropic (only needed for the Anthropic LLM provider)
uv sync --extra web           # + fastapi, uvicorn (the web API)

uv run ruff check .           # lint (add --fix to autofix)
uv run pytest                 # unit tests — OFFLINE, no network (integration deselected by default)
uv run pytest tests/test_analyze.py::test_sentiment_labels   # single test
uv run pytest -k keyword      # tests matching a substring
uv run pytest -m integration  # opt-in live tests — marker registered but UNUSED today (suite is fully offline)

# Run the pipeline (scraping is keyless DuckDuckGo search — no login, no browser)
uv run voc-analyzer run -p "Sony WH-1000XM5" -k "noise cancelling"   # all platforms
uv run voc-analyzer run -p "Sony WH-1000XM5" -P reddit --max-rounds 1
uv run voc-analyzer run -p "Acme Buds" --from-raw data/samples/comments.jsonl   # offline demo, no scraping
uv run voc-analyzer run ... --no-llm        # force rule-based suggestions

# Web app (FastAPI + React SPA)
uv run voc-analyzer-web                      # API on :8000 (dev); set VOC_WEB_STATIC_DIR to also serve the SPA
cd frontend && npm install && npm run dev    # SPA on :5173 (proxies /api → :8000)
```

Reports are written to `data/processed/report.md` + `analysis.json` (override with `--output-dir`).
`pytest` deselects `integration`-marked tests via `addopts` in `pyproject.toml`; CI runs the plain
`uv run pytest` (offline) — so **never assume the network is available in a test**.

## Architecture

Linear pipeline, one package subfolder per stage. Data flows:
`gather (agent-keyworded search→scrape→integrate→analyze, looped) → report`, orchestrated in
`cli.py::run`. By default `run` uses the **agent-driven gathering loop**; `--max-rounds 1` is a
single pass, and `--from-raw` skips gathering entirely.

- **`integrate/schema.py::Comment`** is the contract for the whole system. Every scraper
  produces `Comment`s; everything downstream consumes them. Change it deliberately.
- **`search/`** — `build(product, keywords, platforms)` turns the product + keywords into a
  per-platform dict of query strings. The bare product name is always one of the queries.
- **`gather/`** — `run_gather_loop(...)` is **agent-driven** (LLM in `gather/agent.py`, model
  `VOC_AGENT_MODEL`): the agent `propose_initial_queries` invents round-1 queries from the
  product (`-k` are seeds), then each round runs scrape→integrate→`build_analysis` and the agent
  `decide`s on the *analysis* (sentiment/keywords/quotes via `suggest.payload`) + per-query
  yields whether to stop or propose next queries. **The agent decides**; `target`/diminishing-
  returns are advisory signals, and only `max_rounds` + `max_total` (`config.GATHER_*`) are hard
  backstops. `GatherResult` carries the final `analysis` (CLI reuses it) and `controller`
  (`agent`|`fallback`). No key → deterministic fallback (`search.build` initial + modifier
  escalation). The shared `scrape()` (returns labeled `(platform, query, batch)` tuples) +
  `FETCHERS` live in `scrape/__init__.py`.
- **`scrape/<platform>.py`** — each scraper is a thin **`fetch(query, limit)`** that runs a
  `site:<domain>` DuckDuckGo search via the shared engine and returns `Comment`s. Best-effort:
  on any failure it returns `[]` (a dry scrape is normal, not a crash). Domains: youtube.com,
  reddit.com, tiktok.com, instagram.com, and x.com+twitter.com for `x`.
  - `scrape/_ddgs.py` is the shared engine: live **`search(query, *, site, max_results)`** (calls
    the keyless `ddgs` lib, swallows errors → `[]`) + pure **`parse(results, source) -> list[Comment]`**
    (maps `{title,href,body}` snippets → Comments, drops empty/boilerplate bodies). `parse` is
    unit-tested offline against `data/samples/ddgs_results.json`; `ddgs` is imported lazily.
  - `scrape/_util.py` holds the pure helper `stable_id` (browser-free, formerly in `_browser.py`).
  - **Fidelity caveat**: DDGS returns search *snippets*, not real comments — `author`/`likes` are
    always `None` and `timestamp` is scrape-time. The analysis is directional. See `docs/platforms.md`.
- **`integrate/pipeline.py::integrate`** flattens per-platform batches and `clean`s them:
  NFKC-normalize text → drop <3-char noise → dedupe by native `(source, source_id)` →
  collapse near-duplicate reposts (same source + same alphanumeric-stripped text). Order matters.
- **`analyze/__init__.py::build_analysis`** is the public analysis entry point: it returns the
  single `analysis` dict (sentiment via VADER, keywords/phrases, keywords-by-sentiment, trends,
  representative quotes) that the report renders and `analysis.json` is dumped from.
- **`report/`** — `render.write_report(analysis, out_dir) -> (md_path, json_path)`;
  `suggest.suggest(analysis, use_llm)` returns improvement suggestions, **rule-based by default**,
  switching to the LLM only when a provider is configured (`config.llm_enabled()`), with graceful
  fallback to rule-based on any LLM error. `suggest.summarize(analysis, use_llm)` adds an
  LLM-written **Executive summary** (prose) at the top of the report — LLM-only, omitted
  (returns `""`) without a key. Both are set in `cli.py` onto
  `analysis["suggestions"]`/`["summary"]`; the rest of the report (sentiment, keywords, trends,
  quotes) is always computed locally.
- **`llm.py`** — the single provider-agnostic completion (`complete(system, user, *, model,
  max_tokens)`) used by both `report/suggest.py` and `gather/agent.py`. Dispatches on
  `config.llm_provider()`: `anthropic` (default, lazy `anthropic` SDK, system-as-cacheable-block) or
  `openai` (a plain `httpx` POST to any OpenAI-compatible `/chat/completions` — how free models
  like Qwen are reached; keyless local servers work too — `llm_enabled()` is True for `openai`
  regardless of key). Raises on error; callers own the graceful fallback.

### Front ends (CLI + web share one core)

`_pipeline.py::run_analysis(...)` is the shared orchestration (gather/demo → analyze → enrich
with summary+suggestions), returning an `AnalysisRun`. **Both `cli.py::run` and the web API call
it** — keep new pipeline wiring here, not duplicated. Progress flows through the `on_message`
hook (the CLI passes `console.print`; the web passes a callback that strips rich markup and
pushes to an SSE stream).

`web/` is a **FastAPI** app (`uv sync --extra web`, run via `voc-analyzer-web`): `POST
/api/analyses` starts an in-memory job that runs `run_analysis` in a worker thread
(`asyncio.to_thread`); progress streams over SSE (`GET …/progress`) via
`loop.call_soon_threadsafe` into an `asyncio.Queue`; the `analysis` dict + `report.md`/
`analysis.json` are served from `GET …/{id}` and the download routes. `demo:true` uses the
offline sample path (`tests/test_web.py` is fully offline through it). Jobs are process-local
with no TTL — single uvicorn worker only (v1). The React SPA lives in `frontend/`; in production
FastAPI serves its built `dist/` (set `VOC_WEB_STATIC_DIR`). **LLM keys stay server-side.**

### Cross-file invariant

The set of platforms is hard-coded in **three** places that must stay in sync:
`schema.py::Source` (the `Literal`), `search/__init__.py::PLATFORMS`, and
`scrape/__init__.py::FETCHERS`. Adding a platform = new `scrape/<platform>.py` with a thin
`fetch` (over `_ddgs`), plus an entry in all three.

## Platform reliability (see `docs/platforms.md`)

All five platforms go through the same keyless DuckDuckGo `site:<domain>` search — no login, no
browser, no API keys. **Coverage varies by how well DuckDuckGo indexes each site**: YouTube and
Reddit are good; TikTok/Instagram are patchy; **X is thin** (individual posts are poorly indexed).
Results are search-result **snippets, not real comments** (no author/likes; scrape-time
timestamps), so the analysis is directional. `ddgs` is rate-limited — a throttled query returns
`[]` and the run continues. Boilerplate snippets (JS/login walls) are dropped in `_ddgs.parse`.

## Config (env vars, read in `config.py`)

Scraping: `VOC_DDGS_MAX_RESULTS` (10) · `VOC_DDGS_TIMEOUT_S` (5) · `VOC_DDGS_REGION` (`us-en`) ·
`VOC_DDGS_BACKEND` (`auto`). LLM: `VOC_LLM_PROVIDER` (`anthropic`|`openai`, default `anthropic`) ·
`VOC_LLM_BASE_URL` (OpenAI-compatible endpoint for free models) · `VOC_LLM_API_KEY` (falls back to
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` by provider) · `VOC_LLM_TIMEOUT_S` (60) · `VOC_LLM_MODEL`
(report model) · `VOC_AGENT_MODEL` (gather agent) — both default `claude-sonnet-4-6`; set to the
provider's model id (e.g. a Qwen id) under `openai`. `config.llm_enabled()` gates LLM features.
Gather: `VOC_GATHER_MAX_ROUNDS` (5) · `VOC_GATHER_MAX_TOTAL` (1000) — the two hard backstops ·
advisory `VOC_GATHER_TARGET` (300) / `VOC_GATHER_MIN_NEW` (10) · `VOC_GATHER_MAX_QUERIES` (6) ·
`DATA_DIR`. Loaded from `.env`.

## Conventions

- Ruff: line length 100, rules `E,F,I,B,UP,SIM`, target py311. `from __future__ import annotations` everywhere.
- Tests mirror `src/` structure under `tests/`. Keep `_ddgs.parse` pure so it stays network-free testable.
- Scrapers degrade, never abort: `scrape/__init__.py::scrape` wraps each fetch in try/except so one failing
  platform/query can't take down the run.
