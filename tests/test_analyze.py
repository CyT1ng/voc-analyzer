from datetime import UTC, datetime

from voc_analyzer.analyze import build_analysis, keywords, sentiment, trends
from voc_analyzer.integrate.schema import Comment


def _c(text: str, source: str = "reddit", sid: str | None = None, likes: int = 0, day: int = 1):
    return Comment(
        source=source,
        source_id=sid or text[:12],
        text=text,
        timestamp=datetime(2026, 5, day, tzinfo=UTC),
        url="https://example.com",
        likes=likes,
    )


def test_sentiment_orders_positive_above_negative():
    pos = sentiment.score([_c("I love this, it is amazing and great!")])[0]
    neg = sentiment.score([_c("I hate this, it is terrible and awful.")])[0]
    assert pos > 0 > neg


def test_sentiment_labels():
    assert sentiment.label(0.9) == "positive"
    assert sentiment.label(-0.9) == "negative"
    assert sentiment.label(0.0) == "neutral"


def test_summarize_empty_is_safe():
    summary = sentiment.summarize([])
    assert summary["count"] == 0
    assert summary["mean"] == 0.0


def test_keywords_filter_stopwords_and_product_terms():
    comments = [_c("battery battery life is bad"), _c("the battery died quickly")]
    counts = dict(keywords.extract(comments, extra_stopwords=["life"]))
    assert "battery" in counts
    assert "the" not in counts  # stopword
    assert "life" not in counts  # extra stopword


def test_keywords_by_sentiment_splits_buckets():
    comments = [_c("amazing sound and great battery"), _c("terrible awful battery")]
    scores = sentiment.score(comments)
    split = keywords.extract_by_sentiment(comments, scores)
    assert "positive" in split and "negative" in split


def test_trends_empty_returns_empty_dict():
    assert trends.detect([]) == {}


def test_trends_buckets_by_day():
    comments = [_c("good one", day=1), _c("bad one", day=1), _c("ok one", day=2)]
    result = trends.detect(comments)
    assert result["first_day"] == "2026-05-01"
    assert result["last_day"] == "2026-05-02"
    assert result["peak_day"]["count"] == 2


def test_build_analysis_empty_is_safe():
    analysis = build_analysis([], "Acme")
    assert analysis["totals"]["comments"] == 0
    assert analysis["sentiment"]["mean"] == 0.0
    assert analysis["trends"] == {}


def test_build_analysis_populates_sections():
    comments = [
        _c("amazing sound great battery", likes=10),
        _c("terrible battery awful connection", likes=5),
    ]
    analysis = build_analysis(comments, "Acme Buds")
    assert analysis["totals"]["comments"] == 2
    assert analysis["top_keywords"]
    assert analysis["representative"]["positive"]
    assert analysis["representative"]["negative"]
