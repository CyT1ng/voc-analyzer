"""Improvement suggestions for the report.

Default path is deterministic and rule-based (no network). If an LLM provider is
configured (``config.llm_enabled()``) and ``use_llm`` is on, suggestions are generated
by that model instead — via the provider-agnostic ``voc_analyzer.llm.complete`` — falling
back to the rule-based path on any error.
"""

from __future__ import annotations

import json
import logging
import os
import re

from voc_analyzer import config

log = logging.getLogger(__name__)

# Model id for the report's summary/suggestions; override with VOC_LLM_MODEL. The value
# must match the active provider (e.g. claude-sonnet-4-6 for Anthropic, or a Qwen id like
# qwen/qwen-2.5-72b-instruct when VOC_LLM_PROVIDER=openai).
MODEL = os.getenv("VOC_LLM_MODEL", "claude-sonnet-4-6")
MAX_SUGGESTIONS = 8

_SYSTEM = (
    "You are a senior product analyst writing for the product team that owns "
    "this product. You are given an aggregated Voice-of-Customer analysis of "
    "real social-media comments: sentiment, frequent keywords/phrases split by "
    "sentiment, and verbatim quotes.\n\n"
    "Identify the few DISTINCT underlying problems and strengths the data points "
    "to — synthesize themes, do not just restate individual words. Lean on the "
    "verbatim quotes: they reveal the specific issue behind a keyword (e.g. the "
    "keyword 'anc' may hide a complaint about auto-ANC; 'hinge' may indicate a "
    "structural defect compounded by warranty denials). A feature can be both a "
    "strength and a pain point — say so when the data shows it.\n\n"
    "Write 4-7 suggestions. Each must: name the concrete problem or opportunity, "
    "ground it in the evidence (cite the phrase/keyword or paraphrase a quote), "
    "and state a clear action. Order by apparent severity/frequency. Be specific "
    "and honest about uncertainty when the signal is thin.\n\n"
    "Respond ONLY with a JSON array of suggestion strings — no prose, no "
    "markdown, no surrounding object."
)

_SUMMARY_SYSTEM = (
    "You are a senior product analyst writing a short executive summary for the "
    "product team that owns this product. You are given an aggregated "
    "Voice-of-Customer analysis of real social-media comments: overall sentiment, "
    "frequent keywords/phrases split by sentiment, and verbatim quotes.\n\n"
    "Write 2-3 tight paragraphs (no headings, no bullet lists) a busy PM can read "
    "in 20 seconds: the overall mood and what's driving it, the clearest "
    "strengths, the clearest pain points, and — importantly — an honest caveat "
    "about the data when warranted (thin volume, off-topic or creator-praise "
    "noise, non-English comments, single-platform skew). Synthesize themes from "
    "the evidence; paraphrase quotes rather than inventing specifics, and say so "
    "plainly when the signal is too weak to conclude much.\n\n"
    "Respond with plain prose (markdown allowed) — no preamble like 'Here is', no "
    "JSON, no surrounding heading."
)


def suggest(analysis: dict, use_llm: bool = True, model: str | None = None) -> list[str]:
    """Return improvement suggestions for the given analysis dict."""
    if analysis.get("totals", {}).get("comments", 0) == 0:
        return []
    if use_llm and config.llm_enabled():
        try:
            return _suggest_llm(analysis, model)
        except Exception as exc:  # network, parsing, missing dep — degrade gracefully
            log.warning("LLM suggestions failed (%s); using rule-based fallback", exc)
    return _suggest_rule_based(analysis)


def summarize(analysis: dict, use_llm: bool = True, model: str | None = None) -> str:
    """Return an LLM-written executive summary, or ``""`` when unavailable.

    Unlike suggestions there is no rule-based fallback — a narrative summary is
    inherently an LLM feature, so without a key (or on any error) the section is
    simply omitted.
    """
    if analysis.get("totals", {}).get("comments", 0) == 0:
        return ""
    if use_llm and config.llm_enabled():
        try:
            return _summarize_llm(analysis, model)
        except Exception as exc:  # network, parsing, missing dep — omit gracefully
            log.warning("LLM summary failed (%s); omitting narrative summary", exc)
    return ""


def _suggest_rule_based(analysis: dict) -> list[str]:
    sentiment = analysis.get("sentiment", {})
    distribution = sentiment.get("distribution", {})
    total = sentiment.get("count", 0)
    negative = distribution.get("negative", 0)
    kbs = analysis.get("keywords_by_sentiment", {})
    neg = kbs.get("negative", {})
    pos = kbs.get("positive", {})
    neg_phrases = neg.get("phrases", [])
    neg_keywords = neg.get("keywords", [])
    pos_phrases = pos.get("phrases", [])
    pos_keywords = pos.get("keywords", [])

    def _mentions(n: int) -> str:
        return f"{n} mention" if n == 1 else f"{n} mentions"

    out: list[str] = []
    # Phrases are more specific than single words — surface them first.
    for phrase, count in neg_phrases[:3]:
        out.append(
            f"Recurring complaint about “{phrase}” ({_mentions(count)} in negative "
            f"comments) — investigate the root cause and address it."
        )
    for word, count in neg_keywords[: max(0, 5 - len(out))]:
        out.append(
            f"Users frequently raise “{word}” in negative comments "
            f"({_mentions(count)}) — check the representative quotes for the specifics."
        )
    if total and negative / total > 0.3:
        out.append(
            f"Negative sentiment is elevated ({negative}/{total} comments); "
            "prioritize the complaints above before new features."
        )
    strengths = [p for p, _ in pos_phrases[:2]] + [w for w, _ in pos_keywords[:3]]
    if strengths:
        out.append(f"Preserve current strengths users praise: {', '.join(strengths[:3])}.")
    if not out:
        out.append(
            "No strong negative signal detected; keep monitoring and reinforce "
            "the themes highlighted in positive comments."
        )
    return out[:MAX_SUGGESTIONS]


def payload(analysis: dict) -> dict:
    """Compact projection of the analysis with only the fields useful for an LLM.

    Shared by the report's suggestion/summary calls and by the gather agent's per-round
    evaluation, so the agent and the report see the same distilled view.
    """
    sentiment = analysis.get("sentiment", {})
    representative = analysis.get("representative", {})
    kbs = analysis.get("keywords_by_sentiment", {})

    def _quotes(bucket: str) -> list[str]:
        out = []
        for q in representative.get(bucket, []):
            likes = q.get("likes")
            prefix = f"[{likes} likes] " if likes else ""
            out.append(prefix + q["text"])
        return out

    return {
        "product": analysis.get("product"),
        "keywords_searched": analysis.get("keywords"),
        "comments_analyzed": analysis.get("totals", {}).get("comments"),
        "platforms": analysis.get("platforms"),
        "mean_sentiment": sentiment.get("mean"),
        "sentiment_distribution": sentiment.get("distribution"),
        "negative_keywords": kbs.get("negative", {}).get("keywords"),
        "negative_phrases": kbs.get("negative", {}).get("phrases"),
        "positive_keywords": kbs.get("positive", {}).get("keywords"),
        "positive_phrases": kbs.get("positive", {}).get("phrases"),
        "negative_quotes": _quotes("negative"),
        "positive_quotes": _quotes("positive"),
    }


# Opening fence with an optional language tag, e.g. ```json — newline optional so a
# single-line response like ```json {"a": 1}``` is handled too.
_FENCE_OPEN_RE = re.compile(r"^```[\w-]*[ \t]*\n?")


def strip_fences(text: str) -> str:
    """Strip a Markdown code-fence wrapper from LLM output, if present.

    Shared by the report's LLM calls and the gather agent (``gather/agent.py``).
    """
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE_OPEN_RE.sub("", text, count=1)
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _suggest_llm(analysis: dict, model: str | None = None) -> list[str]:
    from voc_analyzer.llm import complete

    user = (
        "Here is the Voice-of-Customer analysis. Return the JSON array "
        "of improvement suggestions.\n\n"
        + json.dumps(payload(analysis), ensure_ascii=False, indent=2)
    )
    text = complete(_SYSTEM, user, model=model or MODEL, max_tokens=2048)
    data = json.loads(strip_fences(text))
    if isinstance(data, dict):
        data = data.get("suggestions")
    if not isinstance(data, list):
        # Raise so suggest() falls back to the rule-based path — silently accepting e.g. a
        # bare string would iterate its characters and emit one-letter "suggestions".
        raise ValueError(f"expected a JSON array of suggestions, got {type(data).__name__}")
    return [str(item) for item in data][:MAX_SUGGESTIONS]


def _summarize_llm(analysis: dict, model: str | None = None) -> str:
    from voc_analyzer.llm import complete

    user = (
        "Here is the Voice-of-Customer analysis. Write the executive "
        "summary.\n\n" + json.dumps(payload(analysis), ensure_ascii=False, indent=2)
    )
    return complete(_SUMMARY_SYSTEM, user, model=model or MODEL, max_tokens=1024).strip()
