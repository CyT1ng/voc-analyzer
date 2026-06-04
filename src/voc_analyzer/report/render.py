from __future__ import annotations

import json
from pathlib import Path


def _pct(part: int, total: int) -> str:
    return f"{(100 * part / total):.0f}%" if total else "0%"


def _keyword_line(pairs: list) -> str:
    if not pairs:
        return "_none_"
    return ", ".join(f"{word} ({count})" for word, count in pairs)


def _sentiment_section(lines: list[str], analysis: dict) -> None:
    sent = analysis.get("sentiment", {})
    dist = sent.get("distribution", {})
    total = sent.get("count", 0)
    lines.append("## Sentiment\n")
    lines.append(f"Mean compound score: **{sent.get('mean', 0.0):+.3f}**\n")
    lines.append("| Label | Count | Share |")
    lines.append("|-------|-------|-------|")
    for key in ("positive", "neutral", "negative"):
        count = dist.get(key, 0)
        lines.append(f"| {key.capitalize()} | {count} | {_pct(count, total)} |")
    by_platform = sent.get("by_platform", {})
    if by_platform:
        lines.append("\n| Platform | Comments | Mean score |")
        lines.append("|----------|----------|------------|")
        for source, stats in sorted(by_platform.items()):
            lines.append(f"| {source} | {stats['count']} | {stats['mean']:+.3f} |")
    lines.append("")


def _trend_section(lines: list[str], analysis: dict) -> None:
    trends = analysis.get("trends", {})
    by_day = trends.get("by_day", [])
    if not by_day:
        return
    max_count = max(row["count"] for row in by_day)
    lines.append("## Trend over time\n")
    lines.append("| Date | Volume | Mean | |")
    lines.append("|------|--------|------|---|")
    for row in by_day:
        bar = "█" * max(1, round(row["count"] / max_count * 20))
        lines.append(
            f"| {row['date']} | {row['count']} | {row['mean_sentiment']:+.2f} | {bar} |"
        )
    peak = trends.get("peak_day", {})
    if peak:
        lines.append(f"\nPeak day: **{peak['date']}** ({peak['count']} comments).\n")


def _quotes_section(lines: list[str], analysis: dict) -> None:
    rep = analysis.get("representative", {})
    for bucket, heading in (("positive", "👍 Positive"), ("negative", "👎 Negative")):
        quotes = rep.get(bucket, [])
        if not quotes:
            continue
        lines.append(f"## Representative quotes — {heading}\n")
        for q in quotes:
            meta = f"_{q['source']}"
            if q.get("author"):
                meta += f" · {q['author']}"
            if q.get("likes") is not None:
                meta += f" · {q['likes']} likes"
            meta += "_"
            lines.append(f"> {q['text']}\n>\n> {meta} — {q['url']}\n")


def to_markdown(analysis: dict) -> str:
    """Render the analysis dict as a Markdown report."""
    product = analysis.get("product", "(unknown product)")
    lines: list[str] = [f"# Voice of Customer — {product}\n"]

    keywords = analysis.get("keywords") or []
    platforms = analysis.get("platforms") or []
    total = analysis.get("totals", {}).get("comments", 0)
    lines.append(f"- **Keywords:** {', '.join(keywords) if keywords else '(none)'}")
    lines.append(f"- **Platforms:** {', '.join(platforms) if platforms else '(none)'}")
    lines.append(f"- **Comments analyzed:** {total}")
    lines.append(f"- **Generated:** {analysis.get('generated_at', '')}\n")

    if total == 0:
        lines.append("_No comments were collected for this run._\n")
        return "\n".join(lines)

    by_platform = analysis.get("totals", {}).get("by_platform", {})
    if by_platform:
        counts = ", ".join(f"{src}: {n}" for src, n in sorted(by_platform.items()))
        lines.append(f"By platform — {counts}.\n")

    summary = (analysis.get("summary") or "").strip()
    if summary:
        lines.append("## Executive summary\n")
        lines.append(summary + "\n")

    _sentiment_section(lines, analysis)

    lines.append("## Top keywords\n")
    lines.append(_keyword_line(analysis.get("top_keywords", [])) + "\n")
    phrases = analysis.get("top_phrases", [])
    if phrases:
        lines.append(f"**Common phrases:** {_keyword_line(phrases)}\n")
    kbs = analysis.get("keywords_by_sentiment", {})
    pos, neg = kbs.get("positive", {}), kbs.get("negative", {})
    lines.append(f"- **In positive comments:** {_keyword_line(pos.get('keywords', []))}")
    if pos.get("phrases"):
        lines.append(f"  - phrases: {_keyword_line(pos.get('phrases', []))}")
    lines.append(f"- **In negative comments:** {_keyword_line(neg.get('keywords', []))}")
    if neg.get("phrases"):
        lines.append(f"  - phrases: {_keyword_line(neg.get('phrases', []))}")
    lines.append("")

    _trend_section(lines, analysis)
    _quotes_section(lines, analysis)

    suggestions = analysis.get("suggestions", [])
    if suggestions:
        lines.append("## Improvement suggestions\n")
        for i, item in enumerate(suggestions, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    return "\n".join(lines)


def write_report(analysis: dict, out_dir: Path | str) -> tuple[Path, Path]:
    """Write report.md + analysis.json into ``out_dir``; return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    json_path = out_dir / "analysis.json"
    md_path.write_text(to_markdown(analysis), encoding="utf-8")
    json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    return md_path, json_path


def render(analysis: dict, output: Path) -> None:
    """Back-compat shim: write the Markdown report to ``output``."""
    Path(output).write_text(to_markdown(analysis), encoding="utf-8")
