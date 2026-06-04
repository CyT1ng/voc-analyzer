from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voc_analyzer import analyze, config, search
from voc_analyzer.integrate.pipeline import integrate
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.report import render, suggest
from voc_analyzer.scrape import instagram, reddit, tiktok, x, youtube

app = typer.Typer(help="Voice-of-Customer analyzer CLI")
console = Console()

FETCHERS = {
    "youtube": youtube.fetch,
    "reddit": reddit.fetch,
    "tiktok": tiktok.fetch,
    "instagram": instagram.fetch,
    "x": x.fetch,
}


def _load_raw(path: Path) -> list[Comment]:
    """Load unified Comments from a JSONL file (one Comment per line)."""
    comments: list[Comment] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            comments.append(Comment.model_validate_json(line))
    return comments


def _scrape(
    platforms: list[str], queries: dict[str, list[str]], limit: int
) -> list[list[Comment]]:
    batches: list[list[Comment]] = []
    for platform in platforms:
        fetch = FETCHERS[platform]
        for query in queries.get(platform, []):
            try:
                batch = list(fetch(query, limit=limit))
            except Exception as exc:  # one platform/query failing must not abort the run
                console.print(f"[yellow]warn[/yellow] {platform} '{query}': {exc}")
                continue
            if batch:
                console.print(f"  {platform}: {len(batch)} from '{query}'")
            batches.append(batch)
    return batches


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
) -> None:
    """End-to-end run: search → scrape → integrate → analyze → report."""
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
        comments = integrate([_load_raw(from_raw)])
    else:
        console.print(f"[bold]Platforms:[/bold] {', '.join(platforms)}")
        queries = search.build(product, keywords, platforms=tuple(platforms))
        comments = integrate(_scrape(platforms, queries, limit))

    console.print(f"[bold]Collected:[/bold] {len(comments)} unique comments")

    analysis = analyze.build_analysis(comments, product, keywords, platforms)
    analysis["summary"] = suggest.summarize(analysis, use_llm=not no_llm)
    analysis["suggestions"] = suggest.suggest(analysis, use_llm=not no_llm)
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
