"""Reddit scraper — DuckDuckGo ``site:reddit.com`` search.

A thin wrapper over the shared DDGS engine (``scrape/_ddgs.py``). DuckDuckGo indexes
Reddit well and needs no login or residential IP (unlike the old ``.json`` API, which
403'd from datacenter IPs), but it returns page snippets, not full comment trees. See
``docs/platforms.md``. ``fetch`` is best-effort — it returns ``[]`` rather than raising.
"""

from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import _ddgs

SITE = "reddit.com"


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    return _ddgs.parse(_ddgs.search(query, site=SITE, max_results=limit), "reddit")[:limit]
