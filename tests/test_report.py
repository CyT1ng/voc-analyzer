import json
from datetime import UTC, datetime

from voc_analyzer.analyze import build_analysis
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.report import render, suggest


def _analysis():
    comments = [
        Comment(
            source="reddit",
            source_id=str(i),
            text=text,
            timestamp=datetime(2026, 5, 1 + i, tzinfo=UTC),
            url="https://example.com",
            likes=i * 10,
        )
        for i, text in enumerate(
            ["amazing sound and great battery", "terrible battery and awful connection"]
        )
    ]
    return build_analysis(comments, "Acme Buds")


def test_to_markdown_contains_core_sections():
    md = render.to_markdown(_analysis())
    assert "# Voice of Customer — Acme Buds" in md
    assert "## Sentiment" in md
    assert "## Top keywords" in md


def test_to_markdown_empty_is_graceful():
    md = render.to_markdown(build_analysis([], "Acme"))
    assert "No comments" in md


def test_write_report_creates_both_files(tmp_path):
    analysis = _analysis()
    analysis["suggestions"] = suggest.suggest(analysis, use_llm=False)
    md_path, json_path = render.write_report(analysis, tmp_path)
    assert md_path.exists() and json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["product"] == "Acme Buds"


def test_suggest_rule_based_returns_items():
    items = suggest.suggest(_analysis(), use_llm=False)
    assert isinstance(items, list) and items


def test_suggest_empty_analysis_returns_nothing():
    assert suggest.suggest(build_analysis([], "Acme"), use_llm=False) == []


def test_suggest_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr(suggest.config, "anthropic_enabled", lambda: True)
    monkeypatch.setattr(suggest, "_suggest_llm", lambda analysis: ["LLM idea"])
    assert suggest.suggest(_analysis()) == ["LLM idea"]


def test_suggest_falls_back_when_llm_errors(monkeypatch):
    monkeypatch.setattr(suggest.config, "anthropic_enabled", lambda: True)

    def boom(analysis):
        raise RuntimeError("no network")

    monkeypatch.setattr(suggest, "_suggest_llm", boom)
    out = suggest.suggest(_analysis())
    assert out and "LLM idea" not in out
