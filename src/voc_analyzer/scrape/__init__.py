"""W3 — per-platform scrapers. One module per platform.

Also exposes the shared ``FETCHERS`` registry and a CLI-free ``scrape`` helper
that runs a set of per-platform queries and returns one Comment batch per
``(platform, query)``. This lives here (not in ``cli.py``) so both the CLI and
the gathering loop can call it without importing ``rich``/Typer.
"""

from __future__ import annotations

from collections.abc import Callable

from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import instagram, reddit, tiktok, x, youtube

FETCHERS: dict[str, Callable[..., object]] = {
    "youtube": youtube.fetch,
    "reddit": reddit.fetch,
    "tiktok": tiktok.fetch,
    "instagram": instagram.fetch,
    "x": x.fetch,
}


def scrape(
    platforms: list[str],
    queries: dict[str, list[str]],
    limit: int,
    *,
    fetchers: dict[str, Callable[..., object]] | None = None,
    on_message: Callable[[str], None] | None = None,
) -> list[list[Comment]]:
    """Run each platform's queries; return one Comment batch per ``(platform, query)``.

    Each fetch is isolated: a failing platform/query reports via ``on_message`` and is
    skipped rather than aborting the run. ``on_message`` receives human-readable progress
    strings (rich markup allowed); pass ``None`` to stay silent (e.g. in tests).
    """
    fetchers = fetchers or FETCHERS
    batches: list[list[Comment]] = []
    for platform in platforms:
        fetch = fetchers[platform]
        for query in queries.get(platform, []):
            try:
                batch = list(fetch(query, limit=limit))
            except Exception as exc:  # one platform/query failing must not abort the run
                if on_message:
                    on_message(f"[yellow]warn[/yellow] {platform} '{query}': {exc}")
                continue
            if batch and on_message:
                on_message(f"  {platform}: {len(batch)} from '{query}'")
            batches.append(batch)
    return batches
