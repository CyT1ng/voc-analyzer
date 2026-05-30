# Platform notes

Scraping is done with **Playwright** (headless Chromium) against public pages —
no API keys. Each scraper in `src/voc_analyzer/scrape/<platform>.py` splits a
pure `parse(html)` (unit-tested against fixtures in `data/samples/`) from a live
`fetch(query, limit)` that drives the browser via `scrape/_browser.py`.

| Platform   | Login required? | Reliability | Entry point |
|------------|-----------------|-------------|-------------|
| YouTube    | No              | Good        | `youtube.com/results?search_query=…` → video → comments (rendered HTML) |
| Reddit     | No              | IP-dependent | `reddit.com/search.json` → post `.json` (browser `get_json`) |
| TikTok     | Effectively yes | Best-effort | `tiktok.com/search?q=…` |
| Instagram  | Yes             | Best-effort | `instagram.com/explore/tags/<tag>/` |
| X (Twitter)| Yes             | Best-effort | `x.com/search?q=…&f=live` |

**YouTube** is the reliable, login-free path.

**Reddit** uses the public `.json` API (clean structured data, no login) but is
**rate-limited by IP**: from datacenter / cloud / CI / sandbox IPs every endpoint
returns HTTP 403 (verified: bare HTTP, the browser request context, and full page
navigation all 403 from such an IP). From a residential IP it generally works.
On a block it logs a warning and returns `[]` (treated as best-effort), so the
run never fails because of it.

**TikTok / Instagram / X** gate content behind login and anti-bot measures. To
scrape them, set `VOC_BROWSER_PROFILE` to a Chromium profile already signed in to
those sites (and usually `VOC_HEADLESS=false`); otherwise they log a warning and
return nothing rather than failing the run.

## Per-platform selectors

### YouTube (`scrape/youtube.py`)
- Search results → first few `a#video-title` `watch?v=` links.
- Comments: `ytd-comment-view-model` / `ytd-comment-renderer`; text `#content-text`,
  author `#author-text`, likes `#vote-count-middle`, time `#published-time-text a`.
- `source_id` is a stable hash of author+text (no native DOM id).

### Reddit (`scrape/reddit.py`)
- Uses the public `.json` API, not HTML: `old.reddit.com` now redirects to a
  JS-rendered React UI with no stable selectors, so we request
  `search.json` / `{permalink}.json` via `Browser.get_json` (the browser's
  request context) and parse the JSON directly — cleaner and login-free.
- `search.json` → `t3` posts' `permalink` → `{permalink}.json` → walk the comment
  tree (`t1` nodes incl. nested replies; skip `more` placeholders and
  deleted/removed bodies). `source_id` = `name` (`t1_…`), `likes` = `score`,
  timestamp from `created_utc`.
- **IP-blocked from datacenter IPs (403)** — see the reliability note above.
- Reddit search returns nothing for long multi-word phrases, but `search.build`
  always includes the bare product name, which matches.

### TikTok / Instagram / X (best-effort)
- Selectors target the current public DOM (`[data-e2e=…]` for TikTok,
  `article[data-testid="tweet"]` / `[data-testid="tweetText"]` for X, comment
  spans for Instagram) and will drift as the sites change — fix lives in the
  pure `parse()` and its fixture.

## Gotchas

- Selectors break when sites change their markup; the `parse()`/`fetch()` split
  keeps fixes localized and testable without a browser.
- Scraping public pages may conflict with a platform's Terms of Service —
  out of scope to enforce here; use responsibly.
- Run `uv run playwright install chromium` once before any live scrape.
