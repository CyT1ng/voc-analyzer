# Platform notes

Scraping is done with **Playwright** (headless Chromium) against public pages —
no API keys. Each scraper in `src/voc_analyzer/scrape/<platform>.py` splits a
pure `parse(html)` (unit-tested against fixtures in `data/samples/`) from a live
`fetch(query, limit)` that drives the browser via `scrape/_browser.py`.

| Platform   | Login required? | Reliability | Entry URL |
|------------|-----------------|-------------|-----------|
| YouTube    | No              | Good        | `youtube.com/results?search_query=…` → video → comments |
| Reddit     | No              | Good        | `old.reddit.com/search?q=…` → post → comments |
| TikTok     | Effectively yes | Best-effort | `tiktok.com/search?q=…` |
| Instagram  | Yes             | Best-effort | `instagram.com/explore/tags/<tag>/` |
| X (Twitter)| Yes             | Best-effort | `x.com/search?q=…&f=live` |

TikTok / Instagram / X gate content behind login and anti-bot measures. To scrape
them, set `VOC_BROWSER_PROFILE` to a Chromium profile already signed in to those
sites (and usually `VOC_HEADLESS=false`); otherwise those scrapers log a warning
and return nothing rather than failing the run. YouTube and Reddit are the
reliable, login-free paths.

## Per-platform selectors

### YouTube (`scrape/youtube.py`)
- Search results → first few `a#video-title` `watch?v=` links.
- Comments: `ytd-comment-view-model` / `ytd-comment-renderer`; text `#content-text`,
  author `#author-text`, likes `#vote-count-middle`, time `#published-time-text a`.
- `source_id` is a stable hash of author+text (no native DOM id).

### Reddit (`scrape/reddit.py`)
- `old.reddit.com` is server-rendered → clean parsing.
- Search results → `a.search-title` / `a.search-comments` permalinks.
- Comments: `div.thing.comment[data-fullname]`; text `div.usertext-body .md`,
  author `data-author`, score `.score.unvoted[title]`, time `time[datetime]`,
  permalink `data-permalink`. `source_id` = `data-fullname` (`t1_…`).

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
