"""TikTok scraper (Playwright) — best-effort.

TikTok search is heavily protected by anti-bot measures. A logged-in
``VOC_BROWSER_PROFILE`` improves the odds; otherwise this returns an empty list
rather than failing the run.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import Browser, ScrapeError, parse_count, stable_id

BASE = "https://www.tiktok.com"
SEARCH_URL = BASE + "/search?q={q}"


def parse(html: str, source_url: str = BASE, now: datetime | None = None) -> list[Comment]:
    """Parse rendered search/video HTML into Comments (best-effort)."""
    now = now or datetime.now(UTC)
    soup = BeautifulSoup(html, "html.parser")
    out: list[Comment] = []
    for node in soup.select('[data-e2e="search-card-desc"], [data-e2e="comment-level-1"]'):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        container = node.find_parent("div") or node
        like_el = container.select_one('[data-e2e="comment-like-count"]')
        likes = parse_count(like_el.get_text()) if like_el else None
        link = container.select_one('a[href*="/video/"]')
        href = link.get("href") if link else None
        url = urljoin(BASE, href) if href else source_url
        out.append(
            Comment(
                source="tiktok",
                source_id=stable_id("tiktok", text),
                text=text,
                author=None,
                timestamp=now,
                likes=likes,
                url=url,
            )
        )
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    url = SEARCH_URL.format(q=quote_plus(query))
    try:
        with Browser() as browser:
            html = browser.render(url, wait_selector='[data-e2e="search-card-desc"]')
    except ScrapeError:
        return []
    return parse(html, url)[:limit]
