from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment


def fetch(query: str, limit: int = 100) -> Iterable[Comment]:
    raise NotImplementedError("Instagram scraper — implement in W3")
