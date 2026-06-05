"""The agentic gathering loop: cold-start search→scrape→integrate, then repeat with
agent-proposed queries until the agent says "enough" or a guardrail trips.

Reuses the existing pipeline primitives: ``search.build`` (round-1 queries), ``scrape``
(per-round fetching), and the idempotent ``integrate`` (accumulate + dedupe across rounds).
The controller is ``gather.agent`` when an Anthropic key is configured; otherwise a
deterministic modifier-escalation fallback keeps the loop terminating offline.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from voc_analyzer import config, search
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


def _next_decision(
    product: str,
    keywords: list[str],
    round_num: int,
    comments: list[Comment],
    used: set[str],
    target: int,
    use_llm: bool,
) -> dict:
    if use_llm and config.anthropic_enabled():
        try:
            state = agent.build_state(product, keywords, round_num, comments, used)
            return agent.decide(state)
        except Exception as exc:  # network/parse/missing dep — fall back, never crash the run
            log.warning("gather agent failed (%s); using deterministic fallback", exc)
    return _deterministic_decision(product, comments, used, target)


def run_gather_loop(
    product: str,
    keywords: list[str],
    platforms: list[str],
    limit: int,
    *,
    use_llm: bool = True,
    max_rounds: int | None = None,
    target: int | None = None,
    on_message: Callable[[str], None] | None = None,
) -> GatherResult:
    """Gather comments over multiple rounds until enough, then return the deduped set.

    Round 1 is a cold start using ``search.build``; later rounds use the controller's
    proposed queries. ``integrate`` deduplicates across rounds, so ``comments`` is always
    the unique union. Always terminates via max-rounds / target / diminishing-returns guards.
    """
    max_rounds = max_rounds or config.GATHER_MAX_ROUNDS
    target = target or config.GATHER_TARGET

    comments: list[Comment] = []
    used: set[str] = set()
    queries = search.build(product, keywords, platforms=tuple(platforms))
    stop_reason = "max_rounds"
    round_num = 0

    for round_num in range(1, max_rounds + 1):
        queries = _drop_used(queries, used)
        if not any(queries.values()):
            stop_reason = "no_new_queries"
            break
        _record_used(queries, used)

        batches = scrape(platforms, queries, limit, on_message=on_message)
        before = len(comments)
        comments = integrate([comments, *batches])
        added = len(comments) - before
        if on_message:
            on_message(f"  round {round_num}: +{added} new (total {len(comments)})")

        if len(comments) >= target:
            stop_reason = "target_reached"
            break
        if round_num > 1 and added < config.GATHER_MIN_NEW:
            stop_reason = "diminishing_returns"
            break
        if round_num == max_rounds:
            stop_reason = "max_rounds"
            break

        decision = _next_decision(product, keywords, round_num, comments, used, target, use_llm)
        if decision["enough"]:
            stop_reason = "agent_enough"
            break
        if not decision["next_queries"]:
            stop_reason = "agent_no_queries"
            break
        queries = {p: list(decision["next_queries"]) for p in platforms}

    return GatherResult(
        comments=comments,
        rounds=round_num,
        used_queries=sorted(used),
        stop_reason=stop_reason,
    )
