"""X (Twitter) scraper (Playwright) — best-effort.

X gates search behind login and aggressive anti-bot. Set ``VOC_BROWSER_PROFILE``
to a Chromium profile that's already logged in to make this work; otherwise it
returns an empty list rather than failing the whole run.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import Browser, ScrapeError, parse_count, stable_id

BASE = "https://x.com"
SEARCH_URL = BASE + "/search?q={q}&f=live"


def _timestamp(node) -> datetime:
    time_el = node.select_one("time[datetime]")
    if time_el and time_el.get("datetime"):
        try:
            return datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def parse(html: str, source_url: str = BASE) -> list[Comment]:
    """Parse a rendered search timeline into Comments (best-effort)."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[Comment] = []
    for node in soup.select('article[data-testid="tweet"]'):
        text_el = node.select_one('[data-testid="tweetText"]')
        if text_el is None:
            continue
        text = text_el.get_text(" ", strip=True)
        if not text:
            continue
        link = node.select_one('a[href*="/status/"]')
        href = link.get("href") if link else None
        url = urljoin(BASE, href) if href else source_url
        source_id = href.split("/status/")[-1].split("?")[0] if href else stable_id("x", text)
        like_el = node.select_one('[data-testid="like"]')
        likes = parse_count(like_el.get_text()) if like_el else None
        author_el = node.select_one('div[dir="ltr"] span')
        out.append(
            Comment(
                source="x",
                source_id=source_id,
                text=text,
                author=author_el.get_text(strip=True) if author_el else None,
                timestamp=_timestamp(node),
                likes=likes,
                url=url,
            )
        )
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    try:
        with Browser() as browser:
            html = browser.render(
                SEARCH_URL.format(q=quote_plus(query)),
                wait_selector='article[data-testid="tweet"]',
            )
    except ScrapeError:
        return []
    return parse(html, SEARCH_URL.format(q=quote_plus(query)))[:limit]
