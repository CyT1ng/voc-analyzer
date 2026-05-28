# 0001 — Architecture

> Draft. Fill in during W1. Keep it under 2 pages.

## Goal

Given a target e-commerce product, produce an insight report from overseas
social-platform voices in under [target latency, e.g. 1 hour] for [N]
keywords across [M] platforms.

## Non-goals (v0.1)

- Real-time monitoring
- Multi-language analysis beyond English (decide in W1)
- A polished web UI (CLI + static HTML report is enough)

## Pipeline stages

1. **Input** — product name + keyword list
2. **Search** — per-platform query generation
3. **Scrape** — per-platform fetchers, each returns raw records
4. **Integrate** — clean, dedupe, normalize into a unified `Comment` schema
5. **Analyze** — sentiment, keyword extraction, trend detection
6. **Insight** — visualized report + LLM-generated suggestions

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

## Open questions

- Which platforms ship with official APIs that don't need ToS workarounds?
- How do we handle non-English content — translate first, or analyze in-language?
- What's the storage layer for processed data — parquet files, SQLite, DuckDB?

## Decisions log

- (record decisions here as they happen, with date + reason)
