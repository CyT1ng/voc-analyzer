"""Reddit scraper (public ``.json`` API, no auth, no API key) — best-effort.

Reddit's public ``.json`` endpoints return clean structured data (stable ids,
scores, UTC timestamps) — far better than the JS-rendered HTML that
`old.reddit.com` now redirects to. We fetch them through the browser
(``Browser.get_json``) rather than bare ``httpx``.

**Reliability caveat:** Reddit aggressively rate-limits/blocks automated access
by IP. From datacenter / cloud / sandbox IPs every endpoint tends to return
HTTP 403 (verified: bare HTTP, browser request context, and full page
navigation all 403 from such IPs). From a residential IP it generally works.
Because of this, Reddit is treated as **best-effort**: on a block, ``fetch``
logs a warning and returns ``[]`` rather than failing the run.

Flow: prime a session (load the homepage once — Reddit 403s cold ``.json``
requests) → ``/search.json`` → first few post permalinks → each post's
``{permalink}.json`` comment tree → unified ``Comment`` records.

``post_permalinks`` / ``parse_comments`` are pure (JSON in, Comments out) and
unit-tested against committed fixtures; ``fetch`` performs the live request.

Note: Reddit's search dislikes long multi-word queries (a 4+ word phrase often
returns 0 hits), but ``search.build`` always includes the bare product name,
which matches — so per-product coverage is fine.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape._browser import Browser, ScrapeError

log = logging.getLogger(__name__)

BASE = "https://old.reddit.com"
SEARCH_URL = BASE + "/search.json?q={q}&sort=relevance&t=year&limit={limit}"
MAX_POSTS = 6
COMMENTS_PER_POST = 50


def post_permalinks(search_json: dict, limit: int = MAX_POSTS) -> list[str]:
    """Extract post permalinks from a parsed search-results listing."""
    children = search_json.get("data", {}).get("children", [])
    links: list[str] = []
    for child in children:
        if child.get("kind") != "t3":  # t3 = link/post
            continue
        permalink = child.get("data", {}).get("permalink")
        if permalink and permalink not in links:
            links.append(permalink)
        if len(links) >= limit:
            break
    return links


def _comment(data: dict) -> Comment | None:
    body = (data.get("body") or "").strip()
    if not body or body in ("[deleted]", "[removed]"):
        return None
    author = data.get("author")
    if author in ("[deleted]", None, ""):
        author = None
    created = data.get("created_utc")
    ts = datetime.fromtimestamp(created, tz=UTC) if created else datetime.now(UTC)
    permalink = data.get("permalink")
    url = urljoin(BASE, permalink) if permalink else BASE
    return Comment(
        source="reddit",
        source_id=data.get("name") or data.get("id", ""),
        text=body,
        author=author,
        timestamp=ts,
        likes=data.get("score"),
        url=url,
    )


def parse_comments(post_json: list, limit: int = COMMENTS_PER_POST) -> list[Comment]:
    """Parse a post's ``{permalink}.json`` payload (``[post, comments]``) into Comments.

    Walks the comment tree (including nested replies) breadth-first, skipping
    ``more`` placeholders and deleted/removed bodies.
    """
    if not isinstance(post_json, list) or len(post_json) < 2:
        return []
    out: list[Comment] = []
    queue = list(post_json[1].get("data", {}).get("children", []))
    while queue and len(out) < limit:
        child = queue.pop(0)
        if child.get("kind") != "t1":  # skip "more" nodes etc.
            continue
        data = child.get("data", {})
        comment = _comment(data)
        if comment is not None:
            out.append(comment)
        replies = data.get("replies")
        if isinstance(replies, dict):
            queue.extend(replies.get("data", {}).get("children", []))
    return out


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    collected: list[Comment] = []
    with Browser() as browser:
        # Reddit now 403s cold .json requests; load the site once so the request
        # context carries a valid session cookie. Priming is best-effort — if it
        # fails the get_json below will surface the block and degrade to [].
        try:
            browser.prime(BASE + "/")
        except ScrapeError as exc:
            log.warning("reddit session priming failed (%s); trying anyway", exc)
        try:
            search = browser.get_json(SEARCH_URL.format(q=quote_plus(query), limit=MAX_POSTS))
        except ScrapeError as exc:
            # Almost always an IP-level 403 block — best-effort, so don't fail the run.
            log.warning("reddit search blocked (%s); returning no comments", exc)
            return []
        for permalink in post_permalinks(search):
            if len(collected) >= limit:
                break
            try:
                post = browser.get_json(f"{BASE}{permalink}.json?limit={COMMENTS_PER_POST}")
            except ScrapeError:
                continue
            collected.extend(parse_comments(post))
    return collected[:limit]
