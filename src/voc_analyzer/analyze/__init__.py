"""W5–W6 — sentiment, keyword extraction, trend detection.

``build_analysis`` is the package's public entry point: it turns a list of
unified ``Comment`` records into the single ``analysis`` dict that the report
stage renders and that ``analysis.json`` is dumped from.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime

from voc_analyzer.analyze import keywords, sentiment, trends
from voc_analyzer.integrate.schema import Comment


def _quote(comment: Comment, value: float) -> dict:
    return {
        "text": comment.text,
        "source": comment.source,
        "author": comment.author,
        "likes": comment.likes,
        "url": comment.url,
        "score": round(value, 4),
    }


def _representative(comments: list[Comment], scores: list[float], k: int = 3) -> dict:
    """Most-liked clearly-positive and clearly-negative comments as illustrative quotes."""
    pos = [
        (c, s) for c, s in zip(comments, scores, strict=True)
        if s >= sentiment.POSITIVE_THRESHOLD
    ]
    neg = [
        (c, s) for c, s in zip(comments, scores, strict=True)
        if s <= sentiment.NEGATIVE_THRESHOLD
    ]
    pos.sort(key=lambda cs: ((cs[0].likes or 0), cs[1]), reverse=True)
    neg.sort(key=lambda cs: ((cs[0].likes or 0), -cs[1]), reverse=True)
    return {
        "positive": [_quote(c, s) for c, s in pos[:k]],
        "negative": [_quote(c, s) for c, s in neg[:k]],
    }


def build_analysis(
    comments: Iterable[Comment],
    product: str,
    keyword_terms: list[str] | None = None,
    platforms: list[str] | None = None,
    top_k: int = 20,
) -> dict:
    """Assemble the full analysis dict (without LLM suggestions)."""
    comments = list(comments)
    keyword_terms = keyword_terms or []
    extra_stop = [product, *keyword_terms]

    scores = sentiment.score(comments)
    by_platform = Counter(c.source for c in comments)

    return {
        "product": product,
        "keywords": keyword_terms,
        "platforms": platforms or sorted(by_platform),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "totals": {"comments": len(comments), "by_platform": dict(by_platform)},
        "sentiment": sentiment.summarize(comments),
        "top_keywords": keywords.extract(comments, top_k=top_k, extra_stopwords=extra_stop),
        "keywords_by_sentiment": keywords.extract_by_sentiment(
            comments, scores, extra_stopwords=extra_stop
        ),
        "trends": trends.detect(comments),
        "representative": _representative(comments, scores),
        "suggestions": [],
    }
