from datetime import datetime, timezone

from voc_analyzer.integrate.pipeline import dedupe
from voc_analyzer.integrate.schema import Comment


def _c(source_id: str) -> Comment:
    return Comment(
        source="youtube",
        source_id=source_id,
        text="hi",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        url=f"https://youtube.com/{source_id}",
    )


def test_dedupe_removes_same_source_id():
    out = dedupe([_c("a"), _c("a"), _c("b")])
    assert [c.source_id for c in out] == ["a", "b"]
