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


def test_payload_includes_phrases_and_quotes():
    payload = suggest._payload(_analysis())
    assert "negative_phrases" in payload
    assert "positive_phrases" in payload
    assert "negative_quotes" in payload


def test_summarize_no_llm_returns_blank():
    assert suggest.summarize(_analysis(), use_llm=False) == ""


def test_summarize_empty_analysis_returns_blank():
    assert suggest.summarize(build_analysis([], "Acme")) == ""


def test_summarize_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr(suggest.config, "anthropic_enabled", lambda: True)
    monkeypatch.setattr(suggest, "_summarize_llm", lambda analysis: "Overall positive.")
    assert suggest.summarize(_analysis()) == "Overall positive."


def test_summarize_omits_on_llm_error(monkeypatch):
    monkeypatch.setattr(suggest.config, "anthropic_enabled", lambda: True)

    def boom(analysis):
        raise RuntimeError("no network")

    monkeypatch.setattr(suggest, "_summarize_llm", boom)
    assert suggest.summarize(_analysis()) == ""


def test_summarize_llm_sends_payload_and_returns_text(monkeypatch):
    captured = _install_fake_anthropic(monkeypatch, "Solid sentiment overall.")
    out = suggest._summarize_llm(_analysis())
    assert out == "Solid sentiment overall."
    assert "negative_phrases" in captured["messages"][0]["content"]


def test_to_markdown_includes_summary_when_present():
    analysis = _analysis()
    analysis["summary"] = "Customers love the battery but hate the connection."
    md = render.to_markdown(analysis)
    assert "## Executive summary" in md
    assert "love the battery" in md


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


def _install_fake_anthropic(monkeypatch, response_text):
    """Inject a fake ``anthropic`` module so _suggest_llm runs without a real key.

    Returns a dict capturing the kwargs passed to ``messages.create``.
    """
    import sys
    import types

    captured = {}

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeMessage(response_text)

    class _Anthropic:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return captured


def test_suggest_llm_parses_json_array(monkeypatch):
    _install_fake_anthropic(monkeypatch, '["Fix the hinge", "Improve ANC auto mode"]')
    out = suggest._suggest_llm(_analysis())
    assert out == ["Fix the hinge", "Improve ANC auto mode"]


def test_suggest_llm_strips_code_fences_and_unwraps_object(monkeypatch):
    _install_fake_anthropic(monkeypatch, '```json\n{"suggestions": ["a", "b"]}\n```')
    out = suggest._suggest_llm(_analysis())
    assert out == ["a", "b"]


def test_suggest_llm_sends_phrases_in_payload(monkeypatch):
    captured = _install_fake_anthropic(monkeypatch, '["x"]')
    suggest._suggest_llm(_analysis())
    sent = captured["messages"][0]["content"]
    assert "negative_phrases" in sent and "positive_quotes" in sent
