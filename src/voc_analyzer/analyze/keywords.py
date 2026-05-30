from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from voc_analyzer.analyze.sentiment import label
from voc_analyzer.integrate.schema import Comment

# Minimal English stopword set — enough to surface meaningful product terms
# without pulling in a heavyweight NLP dependency.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those", "and", "or", "but",
        "if", "then", "else", "for", "to", "of", "in", "on", "at", "by", "with",
        "from", "as", "is", "are", "was", "were", "be", "been", "being", "do",
        "does", "did", "doing", "have", "has", "had", "having", "i", "you", "he",
        "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
        "his", "its", "our", "their", "mine", "yours", "not", "no", "nor", "so",
        "too", "very", "can", "will", "just", "don", "dont", "didnt", "doesnt",
        "cant", "im", "ive", "id", "ill", "youre", "theyre", "about", "above",
        "after", "again", "against", "all", "am", "any", "because", "before",
        "below", "between", "both", "down", "during", "each", "few", "more",
        "most", "other", "out", "over", "own", "same", "some", "such", "than",
        "up", "only", "also", "get", "got", "really", "would", "could", "should",
        "there", "here", "what", "which", "who", "whom", "when", "where", "why", "how",
    }
)

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]+")


def _tokens(text: str, extra_stop: frozenset[str]) -> list[str]:
    out: list[str] = []
    for match in _TOKEN_RE.findall(text.lower()):
        word = match.strip("'-")
        if len(word) < 3 or word in STOPWORDS or word in extra_stop:
            continue
        out.append(word)
    return out


def _stop_terms(extra_stopwords: Iterable[str] | None) -> frozenset[str]:
    """Tokens from product/keyword terms that we don't want as 'discovered' keywords."""
    if not extra_stopwords:
        return frozenset()
    words: set[str] = set()
    for term in extra_stopwords:
        words.update(re.findall(r"[a-z']+", term.lower()))
    return frozenset(words)


def extract(
    comments: Iterable[Comment],
    top_k: int = 20,
    extra_stopwords: Iterable[str] | None = None,
) -> list[tuple[str, int]]:
    """Top-k keywords by frequency across all comments.

    ``extra_stopwords`` (typically the product name + search keywords) are
    filtered out so results highlight what users say *about* the product rather
    than the product name itself.
    """
    extra_stop = _stop_terms(extra_stopwords)
    counter: Counter[str] = Counter()
    for c in comments:
        counter.update(_tokens(c.text, extra_stop))
    return counter.most_common(top_k)


def extract_by_sentiment(
    comments: Iterable[Comment],
    scores: list[float],
    top_k: int = 15,
    extra_stopwords: Iterable[str] | None = None,
) -> dict[str, list[tuple[str, int]]]:
    """Split top keywords into those from positive vs negative comments."""
    extra_stop = _stop_terms(extra_stopwords)
    buckets: dict[str, Counter[str]] = {"positive": Counter(), "negative": Counter()}
    for c, value in zip(comments, scores, strict=True):
        bucket = label(value)
        if bucket == "neutral":
            continue
        buckets[bucket].update(_tokens(c.text, extra_stop))
    return {name: counter.most_common(top_k) for name, counter in buckets.items()}
