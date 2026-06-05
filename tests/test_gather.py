import sys
import types
from datetime import UTC, datetime

from typer.testing import CliRunner

from voc_analyzer.cli import app
from voc_analyzer.gather import GatherResult, agent, loop, run_gather_loop
from voc_analyzer.integrate.schema import Comment
from voc_analyzer.scrape import scrape

runner = CliRunner()


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


# --- agent.py ---
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


def test_build_state_caps_sample_and_lists_used(monkeypatch):
    monkeypatch.setattr(agent.config, "GATHER_SAMPLE_SIZE", 5)
    comments = [_comment(f"c{i}") for i in range(20)]
    state = agent.build_state("Acme", ["battery"], 2, comments, ["acme", "acme review"])
    assert len(state["sample_comments"]) == 5
    assert state["total_unique_comments"] == 20
    assert state["queries_already_used"] == ["acme", "acme review"]
    assert state["comments_by_platform"] == {"youtube": 20}


def test_normalize_decision_is_defensive(monkeypatch):
    monkeypatch.setattr(agent.config, "GATHER_MAX_QUERIES", 2)
    out = agent._normalize_decision({"next_queries": ["a", "b", "c", "  ", 4]})
    assert out["enough"] is False
    assert out["reason"] == ""
    assert out["next_queries"] == ["a", "b"]  # blanks dropped, coerced, capped at 2
    assert agent._normalize_decision("not a dict") == {
        "enough": False,
        "reason": "",
        "next_queries": [],
    }


# --- loop.py ---
def _enable_llm(monkeypatch):
    monkeypatch.setattr(loop.config, "anthropic_enabled", lambda: True)


def test_loop_stops_when_agent_says_enough(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [[_comment(f"r{n['i']}-{j}") for j in range(3)]]

    decisions = iter(
        [
            {"enough": False, "reason": "", "next_queries": ["more"]},
            {"enough": True, "reason": "ok", "next_queries": []},
        ]
    )
    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(loop.agent, "decide", lambda state: next(decisions))
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert res.stop_reason == "agent_enough"
    assert res.rounds == 2


def test_loop_accumulates_and_dedupes_across_rounds(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    batches = iter(
        [
            [[_comment("a"), _comment("b"), _comment("c")]],
            [[_comment("c"), _comment("d")]],  # 'c' overlaps round 1
        ]
    )
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: next(batches))
    monkeypatch.setattr(
        loop.agent, "decide", lambda s: {"enough": False, "reason": "", "next_queries": ["q2"]}
    )
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=2, target=10_000)
    assert sorted(c.source_id for c in res.comments) == ["a", "b", "c", "d"]  # union, not 5
    assert res.rounds == 2


def test_loop_respects_max_rounds(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [[_comment(f"x{n['i']}")]]

    c = {"i": 0}

    def fake_decide(state):
        c["i"] += 1
        return {"enough": False, "reason": "", "next_queries": [f"q{c['i']}"]}

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(loop.agent, "decide", fake_decide)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.stop_reason == "max_rounds"
    assert res.rounds == 3


def test_loop_target_reached_round_one(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: [[_comment(f"t{j}") for j in range(50)]])
    monkeypatch.setattr(loop.agent, "decide", lambda s: {"enough": False, "next_queries": ["q"]})
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=20)
    assert res.stop_reason == "target_reached"
    assert res.rounds == 1
    assert len(res.comments) >= 20


def test_loop_diminishing_returns(monkeypatch):
    _enable_llm(monkeypatch)  # GATHER_MIN_NEW left at default (10)
    seq = iter(
        [
            [[_comment(f"a{j}") for j in range(15)]],  # round 1: 15 new
            [[]],  # round 2: nothing (login-wall simulation)
        ]
    )
    monkeypatch.setattr(loop, "scrape", lambda *a, **k: next(seq))
    monkeypatch.setattr(loop.agent, "decide", lambda s: {"enough": False, "next_queries": ["q2"]})
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=5, target=10_000)
    assert res.stop_reason == "diminishing_returns"
    assert res.rounds == 2


def test_loop_does_not_rescrape_used_query(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    seen = []
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        seen.append(queries.get("youtube", []))
        n["i"] += 1
        return [[_comment(f"u{n['i']}")]]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(
        loop.agent,
        "decide",
        lambda s: {"enough": False, "next_queries": ["Acme", "Acme fresh"]},
    )
    run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=2, target=10_000)
    assert "Acme" in seen[0]  # round 1 cold-start included the bare product
    assert seen[1] == ["Acme fresh"]  # the re-proposed "Acme" was dropped


def test_loop_deterministic_fallback_without_key(monkeypatch):
    monkeypatch.setattr(loop.config, "anthropic_enabled", lambda: False)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [[_comment(f"d{n['i']}-{j}") for j in range(2)]]

    def boom(state):
        raise AssertionError("agent must not be called without a key")

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(loop.agent, "decide", boom)
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.rounds >= 2  # fallback escalated queries across rounds and terminated
    assert res.comments


def test_loop_agent_error_falls_back(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(loop.config, "GATHER_MIN_NEW", 0)
    n = {"i": 0}

    def fake_scrape(platforms, queries, limit, *, on_message=None, **k):
        n["i"] += 1
        return [[_comment(f"e{n['i']}")]]

    monkeypatch.setattr(loop, "scrape", fake_scrape)
    monkeypatch.setattr(loop.agent, "decide", lambda s: (_ for _ in ()).throw(RuntimeError("down")))
    res = run_gather_loop("Acme", [], ["youtube"], 10, max_rounds=3, target=10_000)
    assert res.rounds >= 2  # fell back to deterministic instead of crashing


# --- scrape extraction ---
def test_scrape_isolates_failures_and_reports():
    msgs = []

    def good(query, limit=100):
        return [_comment("g1")]

    def bad(query, limit=100):
        raise RuntimeError("boom")

    batches = scrape(
        ["youtube", "reddit"],
        {"youtube": ["q"], "reddit": ["q"]},
        10,
        fetchers={"youtube": good, "reddit": bad},
        on_message=msgs.append,
    )
    flat = [c for b in batches for c in b]
    assert [c.source_id for c in flat] == ["g1"]  # good included, bad skipped
    assert any("reddit" in m and "boom" in m for m in msgs)


# --- CLI wiring ---
def test_run_uses_gather_loop(tmp_path, monkeypatch):
    from voc_analyzer import cli

    def fake_loop(product, keywords, platforms, limit, **kw):
        return GatherResult(
            comments=[_comment("k1"), _comment("k2")],
            rounds=2,
            used_queries=["acme"],
            stop_reason="agent_enough",
        )

    monkeypatch.setattr(cli, "run_gather_loop", fake_loop)
    result = runner.invoke(
        app, ["run", "-p", "Acme", "-P", "youtube", "--output-dir", str(tmp_path), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "report.md").exists()
    assert "Gathering:" in result.output
