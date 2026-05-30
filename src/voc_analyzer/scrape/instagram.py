"""Instagram scraper (Playwright) — best-effort.

Instagram requires a logged-in session for almost all content. Point
``VOC_BROWSER_PROFILE`` at a Chromium profile signed in to Instagram to use
this; otherwise it returns an empty list rather than failing the run.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import Browser, ScrapeError, stable_id

BASE = "https://www.instagram.com"
TAG_URL = BASE + "/explore/tags/{tag}/"


def _tag(query: str) -> str:
    return "".join(ch for ch in query.lower() if ch.isalnum())


def parse(html: str, source_url: str = BASE, now: datetime | None = None) -> list[Comment]:
    """Parse rendered post/explore HTML into Comments (best-effort)."""
    now = now or datetime.now(UTC)
    soup = BeautifulSoup(html, "html.parser")
    out: list[Comment] = []
    for node in soup.select("ul li[role='menuitem'] span, div._a9zr span"):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        link = node.find_parent("a")
        href = link.get("href") if link else None
        url = urljoin(BASE, href) if href else source_url
        out.append(
            Comment(
                source="instagram",
                source_id=stable_id("instagram", text),
                text=text,
                author=None,
                timestamp=now,
                likes=None,
                url=url,
            )
        )
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    url = TAG_URL.format(tag=_tag(query))
    try:
        with Browser() as browser:
            html = browser.render(url, wait_selector="article")
    except ScrapeError:
        return []
    return parse(html, url)[:limit]
