"""Gathering controller — an LLM agent (claude-sonnet-4-6) that drives the gather workflow.

Two responsibilities, each an isolated Anthropic call mirroring ``report/suggest.py`` (lazy
import, prompt caching, fence-stripped JSON parsing):

* ``propose_initial_queries`` — invent the first round's search queries from the product.
* ``decide`` — after each round's analysis, judge whether enough has been gathered and, if not,
  propose the next queries to fill the gaps.

Both raise on API/parse error so the caller (``gather/loop.py``) can fall back deterministically.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable

from voc_analyzer import config
from voc_analyzer.report.suggest import payload

AGENT_MODEL = os.getenv("VOC_AGENT_MODEL", "claude-sonnet-4-6")

_INITIAL_SYSTEM = (
    "You are starting a Voice-of-Customer investigation for a product. Propose the first batch "
    "of web/social search queries that will surface real user opinions about it. If seed "
    "keywords are given, treat them as starting hints to EXPAND (features, complaint terms, "
    "use-cases, competitor comparisons); if none are given, work from the product name alone. "
    "Favor diverse, opinion-rich angles (reviews, problems, 'worth it', 'vs', complaints) over "
    "marketing-page phrasing. Keep queries short and search-engine friendly. Every query MUST "
    "name the product (or an unambiguous identifier for it) so results stay on-topic — never use "
    "a generic phrase alone (e.g. 'repair cost', 'battery draining') that would also match "
    "unrelated products or communities.\n\n"
    "Respond ONLY with a JSON object, no prose or markdown:\n"
    '{"queries": ["<query>", "..."]}'
)

_AGENT_SYSTEM = (
    "You are the controller of a Voice-of-Customer gathering loop for a product. After each "
    "round you are given the AGGREGATED ANALYSIS of everything gathered so far (overall "
    "sentiment split, the most frequent keywords/phrases broken down by sentiment, and "
    "representative verbatim quotes), the per-query yields (which query on which platform "
    "returned how many comments), the queries already used, and some advisory signals.\n\n"
    "YOU decide whether to keep gathering. Judge sufficiency by QUALITY and COVERAGE, not raw "
    "count: enough means the analysis paints a clear, multi-faceted picture of what users think "
    "(real strengths AND pain points, on-topic, not dominated by noise like praise for a "
    "reviewer's video). The 'signals' (rough_target, comments_added_last_round, "
    "diminishing_returns, rounds_remaining) are ADVICE you may override — stop early if the "
    "picture is already clear, or keep going past the rough target if it is thin or one-sided. "
    "Use per_query_yields to prefer productive angles and abandon dry ones.\n\n"
    "If NOT enough, propose the next search queries to fill the specific gaps you see (uncovered "
    "features, complaint terms, use-cases, comparisons). Every proposed query MUST name the "
    "product so results stay on-topic. Never repeat a query already used.\n\n"
    "Respond ONLY with a JSON object, no prose or markdown:\n"
    '{"enough": <bool>, "reason": "<one sentence>", "next_queries": ["<query>", ...]}'
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _client_text(system: str, user: str) -> str:
    """Shared Anthropic call: return the concatenated text of the response."""
    from anthropic import Anthropic

    client = Anthropic()
    message = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text")


def _normalize_queries(data: object) -> list[str]:
    """Coerce model output (object with 'queries', or a bare array) into a clean query list."""
    if isinstance(data, dict):
        data = data.get("queries", [])
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        query = str(item).strip()
        if query and query.lower() not in seen:
            seen.add(query.lower())
            out.append(query)
        if len(out) >= config.GATHER_MAX_QUERIES:
            break
    return out


def propose_initial_queries(product: str, keywords: list[str]) -> list[str]:
    """Invent the first round's search queries from the product (``keywords`` are seeds).

    Raises on API/parse error so the loop can fall back to ``search.build``.
    """
    user = (
        "Propose the initial search queries.\n\n"
        + json.dumps({"product": product, "seed_keywords": keywords or []}, ensure_ascii=False)
    )
    return _normalize_queries(json.loads(_strip_fences(_client_text(_INITIAL_SYSTEM, user))))


def build_evaluation(
    product: str,
    analysis: dict,
    per_query_yields: list[dict],
    used_queries: Iterable[str],
    round_num: int,
    *,
    rounds_remaining: int,
    added_last_round: int,
    target_signal: int,
    min_new_signal: int,
    diminishing: bool,
) -> dict:
    """Per-round agent input: the analysis projection + per-query yields + advisory signals."""
    return {
        **payload(analysis),
        "round": round_num,
        "per_query_yields": per_query_yields,
        "queries_already_used": sorted(set(used_queries)),
        "signals": {
            "rough_target": target_signal,
            "comments_added_last_round": added_last_round,
            "min_new_threshold": min_new_signal,
            "diminishing_returns": diminishing,
            "rounds_remaining": rounds_remaining,
        },
    }


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
    """Evaluate the per-round state and decide whether to keep gathering.

    Returns ``{"enough": bool, "reason": str, "next_queries": list[str]}``. Raises on any
    API/parse error so the caller can fall back to a deterministic decision.
    """
    user = (
        "Here is the current gathering state (analysis + yields + signals). Decide whether it "
        "is enough and, if not, what to search next.\n\n"
        + json.dumps(state, ensure_ascii=False, indent=2)
    )
    return _normalize_decision(json.loads(_strip_fences(_client_text(_AGENT_SYSTEM, user))))
