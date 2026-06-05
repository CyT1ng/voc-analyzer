"""Gathering controller — an LLM agent (claude-sonnet-4-6) that decides, each round,
whether enough Voice-of-Customer data has been gathered and, if not, what to search next.

Mirrors the isolated, testable LLM-call pattern in ``report/suggest.py``: a lazy
``anthropic`` import, prompt caching on the system message, and JSON parsing with a
fence-stripping helper. The caller (``gather/loop.py``) handles fallback on any error.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable

from voc_analyzer import config
from voc_analyzer.integrate.schema import Comment

AGENT_MODEL = os.getenv("VOC_AGENT_MODEL", "claude-sonnet-4-6")

_AGENT_SYSTEM = (
    "You are a research controller gathering Voice-of-Customer data about a product. "
    "You are given the current gathering state: how many comments have been collected "
    "(overall and per platform), a sample of the collected comment texts, and the search "
    "queries already used.\n\n"
    "Decide whether enough representative, ON-TOPIC comments have been gathered to write a "
    "useful product analysis. Judge quality, not just count: if the sample is dominated by "
    "off-topic noise (e.g. praise for a reviewer's video rather than the product itself), or "
    "skews to one narrow angle, it is NOT enough. If not enough, propose the next search "
    "queries to fill the gaps — uncovered features, complaint terms, use-cases, or competitor "
    "comparisons. Never repeat a query already used.\n\n"
    "Respond ONLY with a JSON object, no prose or markdown:\n"
    '{"enough": <bool>, "reason": "<one sentence>", "next_queries": ["<query>", ...]}'
)


def _sample(comments: list[Comment], k: int) -> list[str]:
    """Up to ``k`` comment texts, strided across the list for variety."""
    if k <= 0 or not comments:
        return []
    if len(comments) <= k:
        return [c.text for c in comments]
    step = len(comments) / k
    return [comments[int(i * step)].text for i in range(k)]


def build_state(
    product: str,
    keywords: list[str],
    round_num: int,
    comments: list[Comment],
    used_queries: Iterable[str],
) -> dict:
    """Compact, token-bounded snapshot of gathering progress for the agent."""
    by_platform = Counter(c.source for c in comments)
    return {
        "product": product,
        "keywords": keywords,
        "round": round_num,
        "total_unique_comments": len(comments),
        "comments_by_platform": dict(by_platform),
        "queries_already_used": sorted(set(used_queries)),
        "sample_comments": _sample(comments, config.GATHER_SAMPLE_SIZE),
    }


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _normalize_decision(data: object) -> dict:
    """Coerce the model's JSON into a safe ``{enough, reason, next_queries}`` dict."""
    if not isinstance(data, dict):
        return {"enough": False, "reason": "", "next_queries": []}
    raw = data.get("next_queries")
    raw = raw if isinstance(raw, list) else []
    queries = [str(q).strip() for q in raw if str(q).strip()][: config.GATHER_MAX_QUERIES]
    return {
        "enough": bool(data.get("enough")),
        "reason": str(data.get("reason", "")),
        "next_queries": queries,
    }


def decide(state: dict) -> dict:
    """Ask the agent for a gathering decision.

    Returns ``{"enough": bool, "reason": str, "next_queries": list[str]}``. Raises on any
    API/parse error so the caller can fall back to a deterministic decision.
    """
    from anthropic import Anthropic

    client = Anthropic()
    message = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": _AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[
            {
                "role": "user",
                "content": (
                    "Here is the current gathering state. Decide whether it is enough and, "
                    "if not, what to search next.\n\n"
                    + json.dumps(state, ensure_ascii=False, indent=2)
                ),
            }
        ],
    )
    text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
    return _normalize_decision(json.loads(_strip_fences(text)))
