"""TikTok scraper — DuckDuckGo ``site:tiktok.com`` search.

A thin wrapper over the shared DDGS engine (``scrape/_ddgs.py``): results are page
snippets, not video comments, and DuckDuckGo's TikTok coverage is patchy. See
``docs/platforms.md``. ``fetch`` is best-effort — it returns ``[]`` rather than raising.
"""

from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import _ddgs

SITE = "tiktok.com"


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    return _ddgs.parse(_ddgs.search(query, site=SITE, max_results=limit), "tiktok")[:limit]
