from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache

from voc_analyzer.integrate.schema import Comment

# VADER labels above/below this compound threshold; the band between is neutral.
POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05


@lru_cache(maxsize=1)
def _analyzer():
    # Imported lazily so importing this module is cheap and side-effect free.
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def score(comments: Iterable[Comment]) -> list[float]:
    """VADER compound score in [-1, 1] for each comment, aligned by index."""
    analyzer = _analyzer()
    return [analyzer.polarity_scores(c.text)["compound"] for c in comments]


def label(value: float) -> str:
    """Map a compound score to positive / neutral / negative."""
    if value >= POSITIVE_THRESHOLD:
        return "positive"
    if value <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def summarize(comments: Iterable[Comment]) -> dict:
    """Aggregate sentiment: overall mean, label distribution, and per-platform mean."""
    comments = list(comments)
    scores = score(comments)
    if not scores:
        return {
            "count": 0,
            "mean": 0.0,
            "distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "by_platform": {},
        }

    distribution = {"positive": 0, "neutral": 0, "negative": 0}
    per_platform_scores: dict[str, list[float]] = defaultdict(list)
    for comment, value in zip(comments, scores, strict=True):
        distribution[label(value)] += 1
        per_platform_scores[comment.source].append(value)

    by_platform = {
        source: {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4),
        }
        for source, values in per_platform_scores.items()
    }

    return {
        "count": len(scores),
        "mean": round(sum(scores) / len(scores), 4),
        "distribution": distribution,
        "by_platform": by_platform,
    }
