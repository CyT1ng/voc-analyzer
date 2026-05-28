from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment


def score(comments: Iterable[Comment]) -> list[float]:
    raise NotImplementedError("Sentiment scoring — implement in W5")
