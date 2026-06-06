from datetime import UTC, datetime

from voc_analyzer.integrate.pipeline import clean, dedupe, integrate, normalize_text
from voc_analyzer.integrate.schema import Comment


def _c(source_id: str, text: str = "hi there") -> Comment:
    return Comment(
        source="youtube",
        source_id=source_id,
        text=text,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        url=f"https://youtube.com/{source_id}",
    )


def test_dedupe_removes_same_source_id():
    out = dedupe([_c("a"), _c("a"), _c("b")])
    assert [c.source_id for c in out] == ["a", "b"]


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a\n\n b\tc  ") == "a b c"


def test_normalize_text_strips_urls_markdown_and_entities():
    raw = (
        "Check [my review](https://youtube.com/watch?v=abc) and "
        "![pic](https://preview.redd.it/x.jpeg?width=640&amp;format=pjpg&amp;auto=webp) "
        "— battery is great https://example.com/p?utm_source=reddit"
    )
    out = normalize_text(raw)
    assert "my review" in out and "battery is great" in out  # anchor/real text kept
    for junk in ("http", "redd", "jpeg", "pjpg", "webp", "utm", "width"):
        assert junk not in out.lower()  # URL/markup tokens gone


def test_clean_drops_empty_and_too_short():
    out = clean([_c("1", "  hello   world  "), _c("2", "   "), _c("3", "hi")])
    texts = [c.text for c in out]
    assert "hello world" in texts
    assert "hi" not in texts  # below MIN_TEXT_LEN
    assert all(t.strip() for t in texts)


def test_clean_removes_near_duplicate_text():
    out = clean([_c("1", "Great product!"), _c("2", "great   product!!")])
    assert len(out) == 1


def test_integrate_flattens_and_cleans():
    batch_a = [_c("a", "fantastic sound quality")]
    batch_b = [_c("a", "fantastic sound quality"), _c("b", "battery is weak")]
    out = integrate([batch_a, batch_b])
    assert {c.source_id for c in out} == {"a", "b"}
