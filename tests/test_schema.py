from datetime import datetime, timezone

from voc_analyzer.integrate.schema import Comment


def test_comment_minimal_fields():
    c = Comment(
        source="reddit",
        source_id="abc123",
        text="great product",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        url="https://reddit.com/r/x/comments/abc123",
    )
    assert c.source == "reddit"
    assert c.author is None
    assert c.likes is None
    assert c.raw == {}
