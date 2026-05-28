from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="Voice-of-Customer analyzer CLI")
console = Console()


@app.command()
def run(
    product: str = typer.Option(..., "--product", "-p", help="Target product name"),
    keywords: list[str] = typer.Option(None, "--keyword", "-k", help="Keyword(s)"),
) -> None:
    """End-to-end run: search → scrape → integrate → analyze → report."""
    console.print(f"[bold]Product:[/bold] {product}")
    console.print(f"[bold]Keywords:[/bold] {keywords or '(none)'}")
    console.print("[yellow]Pipeline not implemented yet — W1 skeleton.[/yellow]")


@app.command()
def version() -> None:
    from voc_analyzer import __version__

    console.print(__version__)


if __name__ == "__main__":
    app()
