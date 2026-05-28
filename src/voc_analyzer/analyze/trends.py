from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment


def detect(comments: Iterable[Comment]) -> dict:
    raise NotImplementedError("Trend detection — implement in W6")
