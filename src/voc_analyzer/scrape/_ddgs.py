"""Shared DuckDuckGo-search scraping engine for every platform.

Replaces the old Playwright browser: each platform scraper is now a thin wrapper
that runs a ``site:<domain>`` DuckDuckGo search and maps the results into
``Comment`` records. As with the old ``_browser`` split, the live ``search`` (does
IO) is separated from the pure ``parse`` (offline-testable against a JSON fixture).

DuckDuckGo returns search-result **snippets** (a title + a 1-2 sentence body), not
verbatim user comments — so ``author``/``likes`` are always ``None`` and
``timestamp`` is the scrape time. ``ddgs`` is imported lazily so the package (and the
offline parse tests) never need it installed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from voc_analyzer import config
from voc_analyzer.integrate.schema import Comment, Source
from voc_analyzer.scrape._util import stable_id

log = logging.getLogger(__name__)

# DuckDuckGo returns these boilerplate snippets for login-/JS-walled or description-less
# pages (Instagram/X especially). They carry no opinion signal and only pollute keywords.
# Specific phrases are safe to match anywhere in the snippet:
_BOILERPLATE_SUBSTR = (
    "javascript is not available",
    "enable javascript and cookies to continue",
    "the site owner hides the web page description",
    "see posts, photos and more on facebook",
)
# Short, generic phrases that also occur verbatim inside real reviews ("...makes you log in
# to continue, annoying") — only treat them as boilerplate when the whole snippet IS the
# wall/error text, i.e. it starts with the marker.
_BOILERPLATE_PREFIX = (
    "log in to continue",
    "something went wrong. wait a moment",
)


def _is_boilerplate(body: str) -> bool:
    low = body.lower()
    if any(marker in low for marker in _BOILERPLATE_SUBSTR):
        return True
    return any(low.startswith(marker) for marker in _BOILERPLATE_PREFIX)


def search(query: str, *, site: str | None = None, max_results: int | None = None) -> list[dict]:
    """Run a DuckDuckGo text search; return raw result dicts (best-effort).

    ``site`` scopes the search to one domain via the ``site:`` operator. On any
    failure (rate-limit, network, ``ddgs`` not installed) this returns ``[]`` so a
    dry query never aborts the run.
    """
    scoped = f"site:{site} {query}" if site else query
    try:
        from ddgs import DDGS

        results = DDGS(timeout=config.DDGS_TIMEOUT_S).text(
            scoped,
            region=config.DDGS_REGION,
            safesearch="moderate",
            max_results=max_results or config.DDGS_MAX_RESULTS,
            backend=config.DDGS_BACKEND,
        )
        return list(results)
    except Exception as exc:  # rate-limit / network / missing dep — best-effort
        log.warning("ddgs search failed for %r (%s); returning no results", scoped, exc)
        return []


def parse(results: list[dict], source: Source, *, now: datetime | None = None) -> list[Comment]:
    """Map raw DuckDuckGo result dicts into Comments (pure, offline-testable)."""
    now = now or datetime.now(UTC)
    out: list[Comment] = []
    for r in results:
        if not isinstance(r, dict):  # tolerate a malformed element; keep fetch() exception-free
            continue
        body = (r.get("body") or "").strip()
        if not body or _is_boilerplate(body):
            continue
        href = r.get("href") or ""
        title = r.get("title") or ""
        out.append(
            Comment(
                source=source,
                source_id=stable_id(source, href or body),
                text=body,
                author=None,
                timestamp=now,
                likes=None,
                url=href,
                raw={"title": title, "via": "ddgs"},
            )
        )
    return out
