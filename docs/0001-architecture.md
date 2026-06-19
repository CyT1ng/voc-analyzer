# 0001 — Architecture

## Goal

Given a target e-commerce product, produce an insight report from overseas
social-platform voices across up to 5 platforms (YouTube, Reddit, TikTok,
Instagram, X) for a handful of keywords, runnable end-to-end from one CLI
command.

## Non-goals (v0.1)

- Real-time monitoring
- Multi-language analysis beyond English
- A polished web UI (CLI + Markdown/JSON report is enough)
- Guaranteed coverage of login-walled platforms (TikTok/IG/X are best-effort)

## Pipeline stages

1. **Input** — product name + keyword list
2. **Search** — per-platform query generation
3. **Scrape** — per-platform keyless DuckDuckGo (`ddgs`) `site:<domain>` fetchers (no
   browser/login), each returns `Comment` records (best-effort: `[]` on failure)
4. **Integrate** — clean, dedupe, normalize into a unified `Comment` schema
5. **Analyze** — VADER sentiment, keyword extraction, day-bucketed trends
6. **Insight** — Markdown report + `analysis.json`, with rule-based or
   LLM-generated improvement suggestions

## Unified data model (draft)

```python
class Comment:
    source: Literal["youtube", "reddit", "tiktok", "instagram", "x"]
    source_id: str          # platform-native ID
    text: str
    author: str | None
    timestamp: datetime
    likes: int | None
    url: str
    raw: dict               # original payload, kept for debugging
```

## Decisions log

- **2026-05-28 — Scrape via Playwright, not platform APIs.** Avoids per-platform
  API keys/approval (TikTok/IG/X are paywalled or approval-gated). Each scraper
  splits pure parsing from the live `fetch()` so parsing is unit-tested offline
  against committed fixtures and CI needs no browser/network. YouTube works
  without login (reliable). TikTok/IG/X are best-effort and can use a logged-in
  `VOC_BROWSER_PROFILE`.
- **2026-05-28 — Reddit uses the public `.json` API, fetched via the browser.**
  `old.reddit.com` HTML is now a JS React UI with no stable selectors, so we
  request `search.json`/`{permalink}.json` through Playwright's request context
  (`Browser.get_json`) and parse JSON with pure `post_permalinks`/`parse_comments`.
  Reddit rate-limits by IP: datacenter/CI/sandbox IPs get HTTP 403 on every
  endpoint, residential IPs generally work — so Reddit is **best-effort** and
  returns `[]` (with a warning) when blocked.
- **2026-05-28 — Local NLP for analysis, LLM optional.** VADER for sentiment
  (pure-python, social-tuned, deterministic), frequency-based keywords, and
  day-bucketed trends. Report suggestions are rule-based by default; Anthropic
  (Claude) is used only when `ANTHROPIC_API_KEY` is set, with a graceful
  fallback. Keeps the pipeline free, fast, reproducible, and CI-friendly.
- **2026-05-28 — Storage: JSON/JSONL.** `analysis.json` + `report.md` to
  `data/processed/`; raw can be dumped/loaded as JSONL (`--from-raw`). No
  database needed at this scale.
- **2026-05-28 — English-only for v0.1.** Matches the VADER lexicon; revisit if
  non-English volume warrants it.
