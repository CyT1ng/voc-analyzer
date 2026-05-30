"""W2 — keyword/query generation per platform.

Turns a product + optional keyword list into concrete search query strings,
one bundle per platform. The scrapers consume these strings via ``fetch``.
"""

from __future__ import annotations

from voc_analyzer.integrate.schema import Source

PLATFORMS: tuple[Source, ...] = ("youtube", "reddit", "tiktok", "instagram", "x")

# Intent modifiers steer search toward opinion-rich, voice-of-customer content
# rather than marketing pages.
_INTENT_MODIFIERS: tuple[str, ...] = ("review", "problem", "worth it")


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build(
    product: str,
    keywords: list[str] | None = None,
    platforms: tuple[Source, ...] = PLATFORMS,
) -> dict[str, list[str]]:
    """Build per-platform search queries for a product.

    Each keyword is paired with the product; if no keywords are given, the
    product name is combined with generic intent modifiers so we still surface
    opinionated content. The bare product name is always included as a query.
    """

    product = product.strip()
    if not product:
        raise ValueError("product must be a non-empty string")

    cleaned_keywords = [k.strip() for k in (keywords or []) if k and k.strip()]

    base: list[str] = [product]
    if cleaned_keywords:
        base.extend(f"{product} {kw}" for kw in cleaned_keywords)
    else:
        base.extend(f"{product} {mod}" for mod in _INTENT_MODIFIERS)

    queries = _dedupe_preserving_order(base)
    return {platform: list(queries) for platform in platforms}
