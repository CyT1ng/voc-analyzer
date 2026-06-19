"""Pure, browser-free helper shared by the scrapers.

``stable_id`` used to live in ``scrape/_browser.py`` alongside the Playwright wrapper. The
scraping engine is now DuckDuckGo (``scrape/_ddgs.py``), so it lives here with no browser or
network dependency, keeping it trivially unit-testable.
"""

from __future__ import annotations

import hashlib


def stable_id(*parts: str) -> str:
    """Deterministic short id from the given parts (for sources with no native id)."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8", "ignore")).hexdigest()
    return digest[:16]
