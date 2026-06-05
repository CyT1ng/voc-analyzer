"""The agent-driven gathering loop: the agent invents the first round's queries, then each round
runs scrape → integrate → analyze and the agent evaluates that analysis to decide whether to keep
going. Hard backstops (max rounds, max total comments) are the only forced stops; target and
diminishing-returns are advisory signals shown to the agent.

Reuses: ``agent`` (LLM controller), ``search.build`` (keyless round-1 fallback), ``scrape``
(per-round fetching, labeled by query), the idempotent ``integrate`` (accumulate + dedupe), and
``analyze.build_analysis`` (cheap local analysis each round). Without an Anthropic key it falls
back to a deterministic controller so keyless runs still loop and terminate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from voc_analyzer import analyze, config, search
from voc_analyzer.gather import agent
from voc_analyzer.integrate.pipeline import integrate
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import scrape

log = logging.getLogger(__name__)

# Modifiers for the keyless deterministic fallback (superset of search._INTENT_MODIFIERS).
_FALLBACK_MODIFIERS: tuple[str, ...] = (
    "review", "problem", "worth it", "vs", "alternative", "complaints", "issues",
)


@dataclass
class GatherResult:
    comments: list[Comment]
    rounds: int
    used_queries: list[str]
    stop_reason: str
    analysis: dict | None
    controller: str  # "agent" | "fallback" — which controller actually drove the run


def _drop_used(queries: dict[str, list[str]], used: set[str]) -> dict[str, list[str]]:
    return {p: [q for q in qs if q.lower() not in used] for p, qs in queries.items()}


def _record_used(queries: dict[str, list[str]], used: set[str]) -> None:
    for qs in queries.values():
        for q in qs:
            used.add(q.lower())


def _deterministic_decision(
    product: str, comments: list[Comment], used: set[str], target: int
) -> dict:
    """Keyless fallback: escalate unused intent modifiers; stop at target or when exhausted."""
    if len(comments) >= target:
        return {"enough": True, "reason": "target reached", "next_queries": []}
    nexts: list[str] = []
    for mod in _FALLBACK_MODIFIERS:
        query = f"{product} {mod}"
        if query.lower() not in used:
            nexts.append(query)
        if len(nexts) >= config.GATHER_MAX_QUERIES:
            break
    return {"enough": not nexts, "reason": "modifier escalation", "next_queries": nexts}


def _initial_queries(
    product: str, keywords: list[str], platforms: list[str], use_llm: bool
) -> tuple[dict[str, list[str]], str]:
    """Round-1 queries: the agent invents them; fall back to search.build keyless/on error."""
    if use_llm and config.anthropic_enabled():
        try:
            invented = agent.propose_initial_queries(product, keywords)
            if invented:
                return {p: list(invented) for p in platforms}, "agent"
        except Exception as exc:  # network/parse/missing dep — fall back, never crash
            log.warning("initial-query agent failed (%s); using search.build", exc)
    return search.build(product, keywords, platforms=tuple(platforms)), "fallback"


def run_gather_loop(
    product: str,
    keywords: list[str],
    platforms: list[str],
    limit: int,
    *,
    use_llm: bool = True,
    max_rounds: int | None = None,
    target: int | None = None,
    max_total: int | None = None,
    on_message: Callable[[str], None] | None = None,
) -> GatherResult:
    """Gather comments over agent-driven rounds; return the deduped set + final analysis.

    The agent invents round-1 queries and, after each round's analysis, decides whether to keep
    going and what to search next. Hard backstops (``max_rounds``, ``max_total``) always
    terminate; ``target``/diminishing-returns are advisory signals to the agent.
    """
    max_rounds = config.GATHER_MAX_ROUNDS if max_rounds is None else max_rounds
    target = config.GATHER_TARGET if target is None else target
    max_total = config.GATHER_MAX_TOTAL if max_total is None else max_total

    comments: list[Comment] = []
    used: set[str] = set()
    analysis: dict | None = None
    queries, controller = _initial_queries(product, keywords, platforms, use_llm)
    stop_reason = "max_rounds"
    round_num = 0

    for round_num in range(1, max_rounds + 1):
        queries = _drop_used(queries, used)
        if not any(queries.values()):
            stop_reason = "no_new_queries"
            break
        _record_used(queries, used)

        labeled = scrape(platforms, queries, limit, on_message=on_message)
        per_query_yields = [
            {"platform": p, "query": q, "count": len(batch)} for p, q, batch in labeled
        ]
        before = len(comments)
        comments = integrate([comments, *[batch for _, _, batch in labeled]])
        added = len(comments) - before
        analysis = analyze.build_analysis(comments, product, keywords, platforms)
        if on_message:
            on_message(f"  round {round_num}: +{added} new (total {len(comments)})")

        # --- hard backstops only ---
        if len(comments) >= max_total:
            stop_reason = "max_total"
            break
        if round_num == max_rounds:
            stop_reason = "max_rounds"
            break

        # --- agent decides (deterministic fallback when keyless / on error) ---
        diminishing = round_num > 1 and added < config.GATHER_MIN_NEW
        if use_llm and config.anthropic_enabled():
            try:
                state = agent.build_evaluation(
                    product,
                    analysis,
                    per_query_yields,
                    used,
                    round_num,
                    rounds_remaining=max_rounds - round_num,
                    added_last_round=added,
                    target_signal=target,
                    min_new_signal=config.GATHER_MIN_NEW,
                    diminishing=diminishing,
                )
                decision = agent.decide(state)
                controller = "agent"
            except Exception as exc:  # network/parse/missing dep — fall back, never crash
                log.warning("gather agent failed (%s); using deterministic fallback", exc)
                decision = _deterministic_decision(product, comments, used, target)
                controller = "fallback"
        else:
            decision = _deterministic_decision(product, comments, used, target)
            controller = "fallback"

        if decision["enough"]:
            stop_reason = "agent_enough" if controller == "agent" else "fallback_enough"
            break
        if not decision["next_queries"]:
            stop_reason = "agent_no_queries" if controller == "agent" else "fallback_no_queries"
            break
        queries = {p: list(decision["next_queries"]) for p in platforms}

    if analysis is None:  # e.g. max_rounds=0 → zero rounds ran
        analysis = analyze.build_analysis(comments, product, keywords, platforms)

    return GatherResult(
        comments=comments,
        rounds=round_num,
        used_queries=sorted(used),
        stop_reason=stop_reason,
        analysis=analysis,
        controller=controller,
    )
