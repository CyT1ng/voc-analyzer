from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from voc_analyzer.analyze.sentiment import label
from voc_analyzer.integrate.schema import Comment

# Minimal English stopword set — enough to surface meaningful product terms
# without pulling in a heavyweight NLP dependency. Sentiment-bearing words
# (good, bad, love, great, ...) are deliberately kept.
STOPWORDS: frozenset[str] = frozenset(
    {
        # articles / conjunctions / prepositions / pronouns / aux verbs
        "a", "an", "the", "this", "that", "these", "those", "and", "or", "but",
        "if", "then", "else", "for", "to", "of", "in", "on", "at", "by", "with",
        "from", "as", "is", "are", "was", "were", "be", "been", "being", "do",
        "does", "did", "doing", "have", "has", "had", "having", "i", "you", "he",
        "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
        "his", "its", "our", "their", "mine", "yours", "not", "no", "nor", "so",
        "too", "very", "can", "will", "just", "dont", "didnt", "doesnt", "cant",
        "im", "ive", "id", "ill", "youre", "theyre", "about", "above", "after",
        "again", "against", "all", "am", "any", "because", "before", "below",
        "between", "both", "down", "during", "each", "few", "more", "most",
        "other", "out", "over", "own", "same", "some", "such", "than", "up",
        "only", "also", "there", "here", "what", "which", "who", "whom", "when",
        "where", "why", "how",
        # high-frequency conversational filler (carries no product signal)
        "get", "got", "really", "would", "could", "should", "still", "now",
        "use", "used", "using", "thing", "things", "way", "ways", "lot", "bit",
        "going", "gonna", "make", "makes", "made", "want", "wanted", "need",
        "needs", "know", "think", "see", "say", "says", "said", "one", "two",
        "even", "much", "many", "take", "takes", "while", "people", "someone",
        "anyone", "everyone", "something", "anything", "first", "next", "last",
        "time", "actually", "probably", "maybe", "thanks", "thank", "please",
        "yeah", "yes", "okay", "etc",
        # review-medium / web noise (refers to the video, not the product)
        "video", "videos", "review", "reviews", "channel", "subscribe", "watch",
        "comment", "comments", "youtube", "reddit", "https", "http", "www", "com",
    }
)

_TOKEN_RE = re.compile(r"[a-z][a-z'’]+")


def _words(text: str) -> list[str]:
    """Lowercase word tokens with apostrophes removed (it's -> its, don't -> dont)."""
    out: list[str] = []
    for match in _TOKEN_RE.findall(text.lower()):
        word = match.replace("'", "").replace("’", "")
        if word:
            out.append(word)
    return out


def _is_content(word: str, extra_stop: frozenset[str]) -> bool:
    return len(word) >= 3 and word not in STOPWORDS and word not in extra_stop


def _tokens(text: str, extra_stop: frozenset[str]) -> list[str]:
    """Content unigrams from a comment (stopwords and product terms removed)."""
    return [w for w in _words(text) if _is_content(w, extra_stop)]


def _bigrams(text: str, extra_stop: frozenset[str]) -> list[str]:
    """Adjacent content-word pairs, e.g. 'noise cancelling', 'hinge break'.

    Bigrams are formed only from consecutive words that are *both* content words
    in the original text, so stopwords act as phrase boundaries — 'the sound is
    great' yields no bigram, but 'noise cancelling' and 'sound quality' do.
    """
    words = _words(text)
    out: list[str] = []
    for w1, w2 in zip(words, words[1:], strict=False):
        if _is_content(w1, extra_stop) and _is_content(w2, extra_stop):
            out.append(f"{w1} {w2}")
    return out


def _stop_terms(extra_stopwords: Iterable[str] | None) -> frozenset[str]:
    """Tokens from product/keyword terms that we don't want as 'discovered' keywords."""
    if not extra_stopwords:
        return frozenset()
    words: set[str] = set()
    for term in extra_stopwords:
        words.update(w.replace("'", "") for w in re.findall(r"[a-z'’]+", term.lower()))
    return frozenset(words)


def extract(
    comments: Iterable[Comment],
    top_k: int = 20,
    extra_stopwords: Iterable[str] | None = None,
) -> list[tuple[str, int]]:
    """Top-k single-word keywords by frequency across all comments.

    ``extra_stopwords`` (typically the product name + search keywords) are
    filtered out so results highlight what users say *about* the product rather
    than the product name itself.
    """
    extra_stop = _stop_terms(extra_stopwords)
    counter: Counter[str] = Counter()
    for c in comments:
        counter.update(_tokens(c.text, extra_stop))
    return counter.most_common(top_k)


def extract_phrases(
    comments: Iterable[Comment],
    top_k: int = 15,
    extra_stopwords: Iterable[str] | None = None,
    min_count: int = 2,
) -> list[tuple[str, int]]:
    """Top-k two-word phrases that occur at least ``min_count`` times."""
    extra_stop = _stop_terms(extra_stopwords)
    counter: Counter[str] = Counter()
    for c in comments:
        counter.update(_bigrams(c.text, extra_stop))
    return [(phrase, n) for phrase, n in counter.most_common(top_k) if n >= min_count]


def extract_by_sentiment(
    comments: Iterable[Comment],
    scores: list[float],
    top_k: int = 15,
    extra_stopwords: Iterable[str] | None = None,
) -> dict[str, dict[str, list[tuple[str, int]]]]:
    """Top keywords *and* phrases split into positive vs negative comments.

    Returns ``{"positive": {"keywords": [...], "phrases": [...]},
               "negative": {"keywords": [...], "phrases": [...]}}``.
    """
    extra_stop = _stop_terms(extra_stopwords)
    words: dict[str, Counter[str]] = {"positive": Counter(), "negative": Counter()}
    phrases: dict[str, Counter[str]] = {"positive": Counter(), "negative": Counter()}
    for c, value in zip(comments, scores, strict=True):
        bucket = label(value)
        if bucket == "neutral":
            continue
        words[bucket].update(_tokens(c.text, extra_stop))
        phrases[bucket].update(_bigrams(c.text, extra_stop))
    return {
        bucket: {
            "keywords": words[bucket].most_common(top_k),
            "phrases": [(p, n) for p, n in phrases[bucket].most_common(top_k) if n >= 2],
        }
        for bucket in ("positive", "negative")
    }
