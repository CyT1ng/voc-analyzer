from __future__ import annotations

from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment


def dedupe(comments: Iterable[Comment]) -> list[Comment]:
    seen: set[tuple[str, str]] = set()
    out: list[Comment] = []
    for c in comments:
        key = (c.source, c.source_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def clean(comments: Iterable[Comment]) -> list[Comment]:
    raise NotImplementedError("Clean step — implement in W4")
