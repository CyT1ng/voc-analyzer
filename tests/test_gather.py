import sys
import types
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from voc_analyzer.analyze import build_analysis
from voc_analyzer.cli import app
from voc_analyzer.gather import GatherResult, agent, loop, run_gather_loop
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import scrape

runner = CliRunner()


@pytest.fixture(autouse=True)
def _pin_anthropic_provider(monkeypatch):
    # Keep the fake-anthropic agent tests offline regardless of VOC_LLM_PROVIDER in the env.
    monkeypatch.setenv("VOC_LLM_PROVIDER", "anthropic")


def _comment(source_id, source="youtube", text=None):
    return Comment(
        source=source,
        source_id=source_id,
        text=text or f"a genuine comment {source_id} about the product",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        url="https://example.com",
        likes=1,
    )


# --- fake anthropic injection (mirrors tests/test_report.py) ---
class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


def _install_fake_anthropic(monkeypatch, response_text):
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


def _patch_agent(monkeypatch, *, decide, initial=("seed query",)):
    """Enable the LLM path and stub both agent calls (initial queries + per-round decide)."""
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        loop.agent, "propose_initial_queries", lambda product, keywords: list(initial)
    )
    monkeypatch.setattr(loop.agent, "decide", decide)


def _boom(*a, **k):
    raise AssertionError("should not be called")


# --- agent.py: per-round decision ---
def test_decide_parses_json_object(monkeypatch):
    _install_fake_anthropic(
        monkeypatch, '{"enough": false, "reason": "thin", "next_queries": ["acme vs bose"]}'
    )
    out = agent.decide({"product": "Acme"})
    assert out == {"enough": False, "reason": "thin", "next_queries": ["acme vs bose"]}


def test_decide_strips_code_fences(monkeypatch):
    _install_fake_anthropic(
        monkeypatch, '```json\n{"enough": true, "reason": "ok", "next_queries": []}\n```'
    )
    out = agent.decide({"product": "Acme"})
    assert out["enough"] is True and out["next_queries"] == []


def test_decide_uses_sonnet_model(monkeypatch):
    captured = _install_fake_anthropic(
        monkeypatch, '{"enough": true, "reason": "", "next_queries": []}'
    )
    agent.decide({"product": "Acme"})
    assert captured["model"] == "claude-sonnet-4-6"


def test_normalize_decision_is_defensive(monkeypatch):
    monkeypatch.setattr(agent.config, "GATHER_MAX_QUERIES", 2)
    out = agent._normalize_decision({"next_queries": ["a", "b", "c", "  ", 4]})
    assert out == {"enough": False, "reason": "", "next_queries": ["a", "b"]}
    assert agent._normalize_decision("not a dict") == {
        "enough": False,
        "reason": "",
        "next_queries": [],
    }


# --- agent.py: initial-query invention ---
def test_propose_initial_queries_parses_object(monkeypatch):
    _install_fake_anthropic(
        monkeypatch, '{"queries": ["acme review", "acme vs bose", "acme review"]}'
    )
    assert agent.propose_initial_queries("Acme", ["battery"]) == ["acme review", "acme vs bose"]


def test_propose_initial_queries_parses_bare_array(monkeypatch):
    _install_fake_anthropic(monkeypatch, '["q1", "q2"]')
    assert agent.propose_initial_queries("Acme", []) == ["q1", "q2"]


def test_propose_initial_queries_uses_sonnet_model(monkeypatch):
    captured = _install_fake_anthropic(monkeypatch, '{"queries": ["q"]}')
    agent.propose_initial_queries("Acme", [])
    assert captured["model"] == "claude-sonnet-4-6"


def test_propose_initial_queries_caps(monkeypatch):
    monkeypatch.setattr(agent.config, "GATHER_MAX_QUERIES", 2)
    _install_fake_anthropic(monkeypatch, '{"queries": ["a", "b", "c", "d"]}')
    assert agent.propose_initial_queries("Acme", []) == ["a", "b"]


# --- agent.py: analysis-based evaluation state ---
def test_build_evaluation_includes_analysis_yields_and_signals():
    analysis = build_analysis(
        [_comment("a", text="great battery life"), _comment("b", text="bad connection")], "Acme"
    )
    yields = [{"platform": "youtube", "query": "acme review", "count": 2}]
    state = agent.build_evaluation(
        "Acme", analysis, yields, ["acme review"], 2,
        rounds_remaining=3, added_last_round=2, target_signal=300, min_new_signal=10,
        diminishing=False,
    )
    assert "mean_sentiment" in state and "sentiment_distribution" in state  # from payload()
    assert state["per_query_yields"] == yields
    assert state["queries_already_used"] == ["acme review"]
    assert state["round"] == 2
    assert state["signals"]["rough_target"] == 300
    assert state["signals"]["diminishing_returns"] is False


# --- loop.py ---
def test_loop_stops_when_agent_says_enough(monkeypatch):
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    decisions = iter(
        [
            {"enough": False, "reason": "", "next_queries": ["more"]},
            {"enough": True, "reason": "ok", "next_queries": []},
        ]
    )
    _patch_agent(monkeypatch, decide=lambda s: next(decisions))
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [("youtube", "q", [_comment(f"r{n['i']}-{j}") for j in range(3)])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert res.stop_reason == "agent_enough"
    assert res.rounds == 2
    assert res.controller == "agent"


def test_loop_accumulates_and_dedupes_across_rounds(monkeypatch):
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    _patch_agent(monkeypatch, decide=lambda s: {"enough": False, "next_queries": ["q2"]})
    batches = iter(
        [
            [("youtube", "q1", [_comment("a"), _comment("b"), _comment("c")])],
            [("youtube", "q2", [_comment("c"), _comment("d")])],  # 'c' overlaps round 1
        ]
    )
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: next(batches))
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=2, target=10_000)
    assert sorted(c.source_id for c in res.comments) == ["a", "b", "c", "d"]  # union, not 5
    assert res.rounds == 2


def test_loop_respects_max_rounds(monkeypatch):
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    c = {"i": 0}

    def decide(state):
        c["i"] += 1
        return {"enough": False, "next_queries": [f"q{c['i']}"]}

    _patch_agent(monkeypatch, decide=decide)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [("youtube", f"r{n['i']}", [_comment(f"x{n['i']}")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.stop_reason == "max_rounds"
    assert res.rounds == 3


def test_loop_max_total_backstop(monkeypatch):
    _patch_agent(monkeypatch, decide=lambda s: {"enough": False, "next_queries": ["q"]})
    monkeypatch.setattr(
        loop, "scrape", lambda *a, **k: [("youtube", "q", [_comment(f"t{i}") for i in range(50)])]
    )
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000, max_total=20)
    assert res.stop_reason == "max_total"
    assert res.rounds == 1
    assert len(res.comments) >= 20


def test_loop_diminishing_is_signal_not_autostop(monkeypatch):
    states = []
    decisions = iter(
        [
            {"enough": False, "reason": "", "next_queries": ["more"]},
            {"enough": True, "reason": "clear enough", "next_queries": []},
        ]
    )

    def decide(state):
        states.append(state)
        return next(decisions)

    _patch_agent(monkeypatch, decide=decide)
    seq = iter(
        [
            [("youtube", "seed", [_comment(f"a{i}", text=f"t{i}") for i in range(15)])],
            [("youtube", "more", [_comment(f"b{i}", text=f"u{i}") for i in range(3)])],  # < MIN_NEW
        ]
    )
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: next(seq))
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert states[1]["signals"]["diminishing_returns"] is True  # signal shown to the agent
    assert res.stop_reason == "agent_enough"  # the AGENT decided — not a diminishing auto-stop


def test_loop_does_not_rescrape_used_query(monkeypatch):
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    _patch_agent(
        monkeypatch,
        decide=lambda s: {"enough": False, "next_queries": ["Acme", "Acme fresh"]},
        initial=("Acme", "Acme x"),
    )
    seen = []
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        seen.append(queries.get("youtube", []))
        n["i"] += 1
        return [("youtube", "q", [_comment(f"u{n['i']}")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=2, target=10_000)
    assert seen[0] == ["Acme", "Acme x"]  # round-1 queries come from the agent now
    assert seen[1] == ["Acme fresh"]  # the re-proposed "Acme" was dropped as already-used


def test_loop_round1_uses_agent_queries(monkeypatch):
    seen = []

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        seen.append(queries)
        return [("youtube", "x", [_comment("a")])]

    _patch_agent(
        monkeypatch, decide=lambda s: {"enough": True, "next_queries": []}, initial=("agent query",)
    )
    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(loop.search, "build", _boom)  # must NOT cold-start with search.build
    run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=2, target=10_000)
    assert seen[0] == {"youtube": ["agent query"]}


def test_loop_round1_falls_back_to_search_build(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: False)
    seen = []

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        seen.append(queries)
        return [("youtube", "x", [_comment("a")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=1, target=10_000)
    assert "Acme" in seen[0]["youtube"]  # search.build cold-start includes the bare product
    assert res.controller == "fallback"


def test_loop_evaluate_receives_analysis_and_yields(monkeypatch):
    states = []

    def decide(state):
        states.append(state)
        return {"enough": True, "next_queries": []}

    _patch_agent(monkeypatch, decide=decide, initial=("acme review",))

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        return [
            (p, q, [_comment(f"{p}:{q}", text=f"opinion {q}")])
            for p in platforms
            for q in queries.get(p, [])
        ]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert "mean_sentiment" in states[0]
    assert states[0]["per_query_yields"] == [
        {"platform": "youtube", "query": "acme review", "count": 1}
    ]


def test_loop_returns_analysis(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: False)
    monkeypatch.setattr(
        loop, "scrape", lambda *a, **k: [("youtube", "q", [_comment("a"), _comment("b")])]
    )
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=1, target=10_000)
    assert res.analysis is not None
    assert res.analysis["totals"]["comments"] == len(res.comments) == 2


def test_loop_controller_attribution_agent(monkeypatch):
    _patch_agent(monkeypatch, decide=lambda s: {"enough": True, "next_queries": []})
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: [("youtube", "q", [_comment("a")])])
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert res.controller == "agent" and res.stop_reason == "agent_enough"


def test_loop_controller_attribution_fallback(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: False)
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: [("youtube", "q", [_comment("a")])])
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=1)
    assert res.controller == "fallback" and res.stop_reason == "fallback_enough"


def test_loop_agent_error_falls_back(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: True)
    monkeypatch.setattr(loop.agent, "propose_initial_queries", lambda p, k: ["seed"])
    monkeypatch.setattr(loop.agent, "decide", lambda s: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [("youtube", "q", [_comment(f"e{n['i']}")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.controller == "fallback"  # decide raised → deterministic fallback
    assert res.rounds >= 2


def test_loop_deterministic_fallback_without_key(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: False)
    monkeypatch.setattr(loop.agent, "propose_initial_queries", _boom)
    monkeypatch.setattr(loop.agent, "decide", _boom)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [("youtube", "q", [_comment(f"d{n['i']}")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.controller == "fallback"
    assert res.rounds >= 2


def test_loop_explicit_zero_max_rounds(monkeypatch):
    monkeypatch.setattr(loop.config, "llm_enabled", lambda: False)
    called = {"scrape": 0}

    def fake_scrape(*a, **k):
        called["scrape"] += 1
        return [("youtube", "q", [_comment("a")])]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=0, target=10_000)
    assert res.rounds == 0  # the `is None` fix: 0 is honored, not coerced to the default
    assert called["scrape"] == 0
    assert res.analysis is not None


# --- scrape extraction ---
def test_scrape_returns_labeled_tuples():
    def good(query, limit=100):
        return [_comment("g1")]

    def bad(query, limit=100):
        raise RuntimeError("boom")

    result = scrape(
        ["youtube", "reddit"],
        {"youtube": ["q"], "reddit": ["q"]},
        10,
        fetchers={"youtube": good, "reddit": bad},
        on_message=lambda m: None,
    )
    assert [(p, q, [c.source_id for c in b]) for p, q, b in result] == [
        ("youtube", "q", ["g1"]),
        ("reddit", "q", []),  # failed query surfaces as a 0-yield entry
    ]


def test_scrape_isolates_failures_and_reports():
    msgs = []

    def good(query, limit=100):
        return [_comment("g1")]

    def bad(query, limit=100):
        raise RuntimeError("boom")

    result = scrape(
        ["youtube", "reddit"],
        {"youtube": ["q"], "reddit": ["q"]},
        10,
        fetchers={"youtube": good, "reddit": bad},
        on_message=msgs.append,
    )
    flat = [c for _, _, b in result for c in b]
    assert [c.source_id for c in flat] == ["g1"]
    assert any("reddit" in m and "boom" in m for m in msgs)


# --- CLI wiring ---
def test_run_uses_gather_loop(tmp_path, monkeypatch):
    from voc_analyzer import cli

    analysis = build_analysis([_comment("k1"), _comment("k2")], "Acme")

    def fake_loop(product, keywords, platforms, limit, **kw):
        return GatherResult(
            comments=[_comment("k1"), _comment("k2")],
            rounds=2,
            used_queries=["acme"],
            stop_reason="agent_enough",
            analysis=analysis,
            controller="agent",
        )

    monkeypatch.setattr(cli, "run_gather_loop", fake_loop)
    result = runner.invoke(
        app, ["run", "-p", "Acme", "-P", "youtube", "--output-dir", str(tmp_path), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "report.md").exists()
    assert "Gathering:" in result.output and "by agent" in result.output
