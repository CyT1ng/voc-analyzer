"""Reddit scraper (Playwright against old.reddit.com, no API key).

old.reddit.com is server-rendered, so comments come back with stable
``data-fullname`` ids and ISO timestamps — the cleanest of the platforms.
Flow: search → first few post permalinks → each post's comments.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import Browser, ScrapeError, parse_count

BASE = "https://old.reddit.com"
SEARCH_URL = BASE + "/search?q={q}&sort=relevance&t=year"
MAX_POSTS = 5


def post_links(html: str, limit: int = MAX_POSTS) -> list[str]:
    """Extract post permalinks from a search results page."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.select("a.search-title[href], a.search-comments[href]"):
        href = anchor.get("href")
        if href and href not in links:
            links.append(href)
        if len(links) >= limit:
            break
    return links


def _timestamp(node) -> datetime:
    time_el = node.select_one("time[datetime]")
    if time_el and time_el.get("datetime"):
        try:
            return datetime.fromisoformat(time_el["datetime"])
        except ValueError:
            pass
    return datetime.now(UTC)


def parse(html: str, source_url: str = "") -> list[Comment]:
    """Parse a rendered old.reddit comment page into Comments."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[Comment] = []
    for node in soup.select("div.thing.comment[data-fullname]"):
        body = node.select_one("div.entry div.usertext-body .md, div.usertext-body .md")
        if body is None:
            continue
        text = body.get_text(" ", strip=True)
        if not text or text == "[deleted]":
            continue
        fullname = node.get("data-fullname", "")
        author = node.get("data-author") or None
        if author in ("[deleted]", ""):
            author = None
        score_el = node.select_one(".score.unvoted")
        likes = parse_count(score_el.get("title") or score_el.get_text()) if score_el else None
        permalink = node.get("data-permalink")
        url = urljoin(BASE, permalink) if permalink else source_url
        out.append(
            Comment(
                source="reddit",
                source_id=fullname,
                text=text,
                author=author,
                timestamp=_timestamp(node),
                likes=likes,
                url=url,
            )
        )
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    collected: list[Comment] = []
    with Browser() as browser:
        search_html = browser.render(
            SEARCH_URL.format(q=quote_plus(query)),
            wait_selector=".search-result-link, .search-title",
        )
        for link in post_links(search_html):
            if len(collected) >= limit:
                break
            url = link if link.startswith("http") else urljoin(BASE, link)
            try:
                html = browser.render(url, wait_selector="div.commentarea")
            except ScrapeError:
                continue
            collected.extend(parse(html, url))
    return collected[:limit]
