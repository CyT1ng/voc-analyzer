# Platform notes

Scraping is done with **DuckDuckGo search** (the keyless [`ddgs`](https://pypi.org/project/ddgs/)
library) — no browser, no login, no API keys. Each scraper in
`src/voc_analyzer/scrape/<platform>.py` is a thin `fetch(query, limit)` that runs a
`site:<domain>` search via the shared engine `scrape/_ddgs.py` and maps the results
into unified `Comment`s. The live `_ddgs.search` (does IO) is separated from the pure
`_ddgs.parse` (offline-testable against `data/samples/ddgs_results.json`).

| Platform   | Domain searched            | Coverage | Notes |
|------------|----------------------------|----------|-------|
| YouTube    | `youtube.com`              | Good     | Video pages are well indexed |
| Reddit     | `reddit.com`               | Good     | No login / residential IP needed anymore |
| TikTok     | `tiktok.com`               | Patchy   | DuckDuckGo indexes TikTok unevenly |
| Instagram  | `instagram.com`            | Patchy   | Many results are login-walled snippets (filtered) |
| X (Twitter)| `x.com` + `twitter.com`    | Thin     | Individual posts are poorly indexed |

## Fidelity caveat (important)

DuckDuckGo returns **search-result snippets** (a title + a 1–2 sentence body), **not
verbatim user comments or full threads**. Consequences for every `Comment`:

- `author` and `likes` are always `None` (snippets carry no author/engagement).
- `timestamp` is the scrape time, not when the content was posted (so the trend-over-time
  section reflects when you ran the tool, not real posting dates).
- `text` is a page snippet describing the product, which may be an article blurb or a
  paraphrase rather than a real opinion.

So treat the analysis as **directional**: it surfaces what's being said *about* the product
across these sites, but it is lower-fidelity and lower-volume than reading the actual comment
threads. Login-/JS-walled boilerplate snippets ("JavaScript is not available", "the site
owner hides the web page description", …) are dropped in `_ddgs.parse` so they don't pollute
keywords, but some thin/off-topic snippets will still get through.

## Reliability & rate limits

- `ddgs` is keyless and **rate-limited by DuckDuckGo**. The gather loop fires
  `platforms × queries` searches per round, so large runs can get throttled; a throttled
  search returns `[]` (logged as a warning) and the run continues — a dry round just looks
  low-yield to the gather agent. If you hit throttling, lower `VOC_GATHER_MAX_QUERIES` or
  `VOC_DDGS_MAX_RESULTS`, or reduce `--max-rounds`.
- Every `fetch` is best-effort: on any failure it returns `[]` rather than raising, and
  `scrape/__init__.py::scrape` further isolates each query, so one dry platform never aborts
  the run.

## Tuning (env vars)

`VOC_DDGS_MAX_RESULTS` (10) · `VOC_DDGS_TIMEOUT_S` (5) · `VOC_DDGS_REGION` (`us-en`) ·
`VOC_DDGS_BACKEND` (`auto`). See `config.py`.

## Gotchas

- Scraping/indexing public pages may conflict with a platform's Terms of Service — out of
  scope to enforce here; use responsibly.
- DuckDuckGo result quality drifts; when a platform suddenly returns little, it's usually
  index coverage, not a code bug. The `search()`/`parse()` split keeps any parsing fix
  localized and testable without network.
