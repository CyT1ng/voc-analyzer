from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment


def extract(comments: Iterable[Comment], top_k: int = 20) -> list[tuple[str, int]]:
    raise NotImplementedError("Keyword extraction — implement in W5")
