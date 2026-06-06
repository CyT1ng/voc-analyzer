from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable

from voc_analyzer.integrate.schema import Comment

# Comments shorter than this (after cleaning) carry no analytic signal.
MIN_TEXT_LEN = 3

_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# URLs and markdown links pollute keyword/phrase extraction with junk tokens
# (e.g. Reddit image embeds → "preview redd", "jpeg width", "amp format"). Drop the
# URL but keep human anchor text.
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")  # ![alt](url) → removed entirely
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")  # [text](url) → text
_URL_RE = re.compile(r"(?:https?://|www\.)\S+")  # bare URLs → removed


def normalize_text(text: str) -> str:
    """Normalize unicode, drop URLs/markdown links, strip control chars, collapse whitespace."""
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub(" ", text)
    text = _CONTROL_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def dedupe(comments: Iterable[Comment]) -> list[Comment]:
    """Drop records sharing a (source, source_id) — the platform-native identity."""
    seen: set[tuple[str, str]] = set()
    out: list[Comment] = []
    for c in comments:
        key = (c.source, c.source_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _text_key(c: Comment) -> tuple[str, str]:
    """Identity for near-duplicate detection: same source + same normalized text."""
    return (c.source, re.sub(r"[^a-z0-9]+", "", c.text.lower()))


def dedupe_text(comments: Iterable[Comment]) -> list[Comment]:
    """Drop reposts: different IDs but identical text within the same source."""
    seen: set[tuple[str, str]] = set()
    out: list[Comment] = []
    for c in comments:
        key = _text_key(c)
        if key[1] and key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def clean(comments: Iterable[Comment]) -> list[Comment]:
    """Normalize text, drop noise/empties, and remove duplicates.

    Order matters: normalize first so dedup keys are stable, then drop empties,
    then dedup by native id, then collapse near-identical reposts.
    """
    normalized: list[Comment] = []
    for c in comments:
        text = normalize_text(c.text)
        if len(text) < MIN_TEXT_LEN:
            continue
        normalized.append(c.model_copy(update={"text": text}))
    return dedupe_text(dedupe(normalized))


def integrate(per_source: Iterable[Iterable[Comment]]) -> list[Comment]:
    """Flatten per-platform scrape results into one cleaned, unified list."""
    flat: list[Comment] = [c for batch in per_source for c in batch]
    return clean(flat)
