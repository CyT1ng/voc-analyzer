"""Shared analysis core used by both the CLI (`cli.py`) and the web API (`web/`).

`run_analysis` is the single orchestration of gather → analyze → enrich, factored out of
`cli.py::run` so the two front ends can never drift. It has no Typer/rich/FastAPI dependency;
progress is reported through the optional `on_message` callback (the same hook the gather loop
and scrapers use).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from voc_analyzer import analyze, config
from voc_analyzer.gather import run_gather_loop
from voc_analyzer.integrate.pipeline import integrate
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.report import suggest

log = logging.getLogger(__name__)

OnMessage = Callable[[str], None]


@dataclass
class AnalysisRun:
    """Result of `run_analysis`: the report-ready analysis dict plus gather metadata."""

    analysis: dict
    comment_count: int
    rounds: int | None = None
    stop_reason: str | None = None
    controller: str | None = None


def load_comments(path: Path, on_message: OnMessage | None = None) -> list[Comment]:
    """Load unified Comments from a JSONL file (one per line).

    Malformed lines are skipped with a warning (via `on_message`, else the logger); a read
    error (missing/unreadable file) raises `OSError` for the caller to translate.
    """
    text = path.read_text(encoding="utf-8")  # OSError propagates to the caller
    out: list[Comment] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Comment.model_validate_json(line))
        except ValidationError:
            warn = f"[yellow]warn[/yellow] {path.name}:{lineno}: skipping malformed line"
            (on_message or log.warning)(warn)
    return out


def run_analysis(
    product: str,
    keywords: list[str],
    platforms: list[str],
    *,
    limit: int = 100,
    use_llm: bool = True,
    max_rounds: int | None = None,
    target: int | None = None,
    max_total: int | None = None,
    demo: bool = False,
    raw_path: Path | None = None,
    model: str | None = None,
    on_message: OnMessage | None = None,
) -> AnalysisRun:
    """Run the full pipeline and return a report-ready analysis dict.

    Three input modes: `demo` (the bundled sample JSONL), `raw_path` (a given JSONL), or — by
    default — the live agent-driven gather loop. In every mode the LLM summary/suggestions are
    attached (subject to `use_llm` and a configured provider).
    """
    rounds = stop_reason = controller = None
    if demo or raw_path is not None:
        path = raw_path or (config.SAMPLES_DIR / "comments.jsonl")
        comments = integrate([load_comments(path, on_message)])
        if on_message:
            on_message(f"  loaded {len(comments)} comments from {path.name}")
        # Platforms are derived from the data, not the requested list.
        analysis = analyze.build_analysis(comments, product, keywords)
    else:
        result = run_gather_loop(
            product,
            keywords,
            platforms,
            limit,
            use_llm=use_llm,
            max_rounds=max_rounds,
            target=target,
            max_total=max_total,
            on_message=on_message,
        )
        comments = result.comments
        analysis = result.analysis  # computed inside the loop; no recompute
        rounds, stop_reason, controller = result.rounds, result.stop_reason, result.controller

    if on_message:
        on_message("Generating insights…")
    analysis["summary"] = suggest.summarize(analysis, use_llm=use_llm, model=model)
    analysis["suggestions"] = suggest.suggest(analysis, use_llm=use_llm, model=model)
    return AnalysisRun(
        analysis=analysis,
        comment_count=len(comments),
        rounds=rounds,
        stop_reason=stop_reason,
        controller=controller,
    )
