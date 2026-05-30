from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from voc_analyzer.analyze.sentiment import score
from voc_analyzer.integrate.schema import Comment


def detect(comments: Iterable[Comment]) -> dict:
    """Bucket comments by UTC day, reporting volume and mean sentiment over time.

    Returns ``{}`` for empty input. Otherwise:
        {
          "by_day": [{"date": "2026-01-01", "count": 3, "mean_sentiment": 0.42}, ...],
          "first_day": "2026-01-01",
          "last_day": "2026-01-05",
          "peak_day": {"date": "2026-01-03", "count": 9, "mean_sentiment": -0.1},
        }
    """
    comments = list(comments)
    if not comments:
        return {}

    scores = score(comments)
    by_day_scores: dict[str, list[float]] = defaultdict(list)
    for c, value in zip(comments, scores, strict=True):
        day = c.timestamp.date().isoformat()
        by_day_scores[day].append(value)

    by_day = [
        {
            "date": day,
            "count": len(values),
            "mean_sentiment": round(sum(values) / len(values), 4),
        }
        for day, values in sorted(by_day_scores.items())
    ]
    peak = max(by_day, key=lambda row: row["count"])

    return {
        "by_day": by_day,
        "first_day": by_day[0]["date"],
        "last_day": by_day[-1]["date"],
        "peak_day": peak,
    }
