"""YouTube scraper (Playwright, no API key).

Flow: search results page → first few videos → each video's comment section
(scrolled to load lazily) → unified ``Comment`` records. ``parse`` is pure and
unit-tested against a saved HTML fixture; ``fetch`` drives the live browser.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import (
    Browser,
    ScrapeError,
    parse_count,
    relative_time,
    stable_id,
)

SEARCH_URL = "https://www.youtube.com/results?search_query={q}"
WATCH_URL = "https://www.youtube.com/watch?v={vid}"
MAX_VIDEOS = 3


def video_ids(html: str, limit: int = MAX_VIDEOS) -> list[str]:
    """Extract the first video ids from a search results page."""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    for anchor in soup.select("a#video-title[href], a.yt-simple-endpoint[href*='watch?v=']"):
        href = anchor.get("href", "")
        if "watch?v=" not in href:
            continue
        vid = href.split("watch?v=")[1].split("&")[0]
        if vid and vid not in ids:
            ids.append(vid)
        if len(ids) >= limit:
            break
    return ids


def parse(html: str, source_url: str = "", now: datetime | None = None) -> list[Comment]:
    """Parse rendered video-page HTML into Comments."""
    now = now or datetime.now(UTC)
    soup = BeautifulSoup(html, "html.parser")
    out: list[Comment] = []
    for node in soup.select("ytd-comment-view-model, ytd-comment-renderer"):
        text_el = node.select_one("#content-text")
        if text_el is None:
            continue
        text = text_el.get_text(" ", strip=True)
        if not text:
            continue
        author_el = node.select_one("#author-text")
        author = author_el.get_text(strip=True) if author_el else None
        likes_el = node.select_one("#vote-count-middle")
        likes = parse_count(likes_el.get_text(strip=True)) if likes_el else None
        time_el = node.select_one("#published-time-text a, .published-time-text")
        ts = relative_time(time_el.get_text(strip=True), now) if time_el else now
        out.append(
            Comment(
                source="youtube",
                source_id=stable_id("youtube", author or "", text),
                text=text,
                author=author,
                timestamp=ts,
                likes=likes,
                url=source_url,
            )
        )
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    collected: list[Comment] = []
    with Browser() as browser:
        search_html = browser.render(
            SEARCH_URL.format(q=quote_plus(query)), wait_selector="a#video-title"
        )
        for vid in video_ids(search_html):
            if len(collected) >= limit:
                break
            url = WATCH_URL.format(vid=vid)
            try:
                html = browser.render(url, wait_selector="#content-text")
            except ScrapeError:
                continue
            collected.extend(parse(html, url))
    return collected[:limit]
