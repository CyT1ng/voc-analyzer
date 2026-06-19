"""X (Twitter) scraper — DuckDuckGo search over ``x.com`` + ``twitter.com``.

A thin wrapper over the shared DDGS engine (``scrape/_ddgs.py``). Both domains are
covered in a single ``(site:x.com OR site:twitter.com)`` query to keep the rate-limit
footprint low. DuckDuckGo indexes individual posts poorly, so X coverage is **thin** and
results are snippets, not the post text. See ``docs/platforms.md``. ``fetch`` is
best-effort — it returns ``[]`` rather than raising.
"""

from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import _ddgs

# Scope is baked into the query (the OR operator), so _ddgs.search is called with site=None.
_SCOPE = "(site:x.com OR site:twitter.com)"


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    results = _ddgs.search(f"{_SCOPE} {query}", max_results=limit)
    return _ddgs.parse(results, "x")[:limit]
