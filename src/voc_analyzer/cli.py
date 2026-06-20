from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voc_analyzer import _pipeline, config
from voc_analyzer.report import render
from voc_analyzer.scrape import FETCHERS

app = typer.Typer(help="Voice-of-Customer analyzer CLI")
console = Console()


@app.command()
def run(
    product: str = typer.Option(..., "--product", "-p", help="Target product name"),
    keywords: list[str] = typer.Option(None, "--keyword", "-k", help="Keyword(s)"),
    platforms: list[str] = typer.Option(
        None, "--platform", "-P", help=f"Platforms to scrape (default: all of {list(FETCHERS)})"
    ),
    limit: int = typer.Option(100, "--limit", help="Max comments per query"),
    output_dir: Path = typer.Option(
        None, "--output-dir", help="Where to write report.md + analysis.json"
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM suggestions"),
    from_raw: Path = typer.Option(
        None, "--from-raw", help="Load Comments from a JSONL file instead of scraping"
    ),
    max_rounds: int = typer.Option(
        None, "--max-rounds", help="Max gathering rounds (hard cap; 1 = single pass)"
    ),
    target: int = typer.Option(
        None, "--target", help="Advisory 'enough' target shown to the agent (not a hard stop)"
    ),
    max_total: int = typer.Option(
        None, "--max-total", help="Hard cap on total comments gathered (safety backstop)"
    ),
) -> None:
    """End-to-end run: gather (search→scrape→integrate, looped) → analyze → report."""
    keywords = keywords or []
    platforms = platforms or list(FETCHERS)
    unknown = [p for p in platforms if p not in FETCHERS]
    if unknown:
        raise typer.BadParameter(f"unknown platform(s): {unknown}; choose from {list(FETCHERS)}")
    out_dir = output_dir or config.PROCESSED_DIR

    console.print(f"[bold]Product:[/bold] {product}")
    console.print(f"[bold]Keywords:[/bold] {keywords or '(none)'}")

    if from_raw is not None:
        console.print(f"[bold]Source:[/bold] {from_raw}")
        try:
            run_result = _pipeline.run_analysis(
                product,
                keywords,
                platforms,
                raw_path=from_raw,
                use_llm=not no_llm,
                on_message=console.print,
            )
        except OSError as exc:
            raise typer.BadParameter(f"cannot read --from-raw file: {exc}") from exc
    else:
        console.print(f"[bold]Platforms:[/bold] {', '.join(platforms)}")
        run_result = _pipeline.run_analysis(
            product,
            keywords,
            platforms,
            limit=limit,
            use_llm=not no_llm,
            max_rounds=max_rounds,
            target=target,
            max_total=max_total,
            on_message=console.print,
        )
        console.print(
            f"[bold]Gathering:[/bold] {run_result.rounds} round(s) — "
            f"stopped: {run_result.stop_reason} (by {run_result.controller})"
        )

    analysis = run_result.analysis
    console.print(f"[bold]Collected:[/bold] {run_result.comment_count} unique comments")
    md_path, json_path = render.write_report(analysis, out_dir)

    _print_summary(analysis)
    console.print(f"\n[green]Report:[/green] {md_path}\n[green]Data:[/green]   {json_path}")


def _print_summary(analysis: dict) -> None:
    total = analysis["totals"]["comments"]
    if total == 0:
        console.print("[yellow]No comments collected — wrote an empty report.[/yellow]")
        return
    dist = analysis["sentiment"]["distribution"]
    table = Table(title="Sentiment")
    table.add_column("Label")
    table.add_column("Count", justify="right")
    for key in ("positive", "neutral", "negative"):
        table.add_row(key.capitalize(), str(dist.get(key, 0)))
    console.print(table)
    top = analysis.get("top_keywords", [])[:8]
    if top:
        console.print("Top keywords: " + ", ".join(f"{w} ({c})" for w, c in top))


@app.command()
def version() -> None:
    from voc_analyzer import __version__

    console.print(__version__)


if __name__ == "__main__":
    app()
