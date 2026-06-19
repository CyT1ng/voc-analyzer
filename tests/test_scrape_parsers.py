import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

from voc_analyzer.scrape import _ddgs, instagram, reddit, tiktok, x, youtube
from voc_analyzer.scrape._util import stable_id

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def _results():
    return json.loads((SAMPLES / "ddgs_results.json").read_text(encoding="utf-8"))


# --- DDGS parse (pure, offline) ---
def test_ddgs_parse_maps_results_to_comments():
    now = datetime(2026, 6, 1, tzinfo=UTC)
    comments = _ddgs.parse(_results(), "youtube", now=now)
    # the empty-body third result is skipped
    assert len(comments) == 2
    first = comments[0]
    assert first.source == "youtube"
    assert first.text.startswith("The ANC is amazing")
    assert first.url == "https://www.youtube.com/watch?v=abc123"
    assert first.author is None and first.likes is None
    assert first.timestamp == now
    assert first.raw["via"] == "ddgs"
    assert first.raw["title"].startswith("Sony WH-1000XM5")


def test_ddgs_parse_ids_are_deterministic_and_distinct():
    a = _ddgs.parse(_results(), "youtube")
    b = _ddgs.parse(_results(), "youtube")
    assert [c.source_id for c in a] == [c.source_id for c in b]  # deterministic
    assert a[0].source_id != a[1].source_id  # distinct hrefs → distinct ids (protects dedupe)


def test_ddgs_parse_uses_source_argument():
    comments = _ddgs.parse(_results(), "reddit")
    assert all(c.source == "reddit" for c in comments)


def test_ddgs_parse_drops_boilerplate_snippets():
    noisy = [
        {"title": "x", "href": "https://x.com/a", "body": "JavaScript is not available."},
        {"title": "ig", "href": "https://instagram.com/b",
         "body": "The site owner hides the web page description."},
        {"title": "wall", "href": "https://x.com/d",
         "body": "Log in to continue. Don't have an account? Sign up."},  # prefix marker
        {"title": "real", "href": "https://reddit.com/c", "body": "Genuinely great battery life."},
    ]
    comments = _ddgs.parse(noisy, "x")
    assert [c.text for c in comments] == ["Genuinely great battery life."]


def test_ddgs_parse_keeps_reviews_that_merely_mention_boilerplate_phrases():
    # The generic markers are prefix-anchored, so they must NOT match mid-sentence in a
    # real complaint (only a snippet that *is* the wall/error text — i.e. starts with it).
    reviews = [
        {"title": "a", "href": "https://reddit.com/a",
         "body": "Great headphones but the app makes you log in to continue, super annoying."},
        {"title": "b", "href": "https://reddit.com/b",
         "body": "Worst part: it says something went wrong. wait a moment, constantly."},
    ]
    comments = _ddgs.parse(reviews, "reddit")
    assert len(comments) == 2


def test_ddgs_parse_tolerates_non_dict_elements():
    # parse must never raise on malformed results, so fetch() stays exception-free.
    assert _ddgs.parse(["junk", None, 123], "youtube") == []


# --- DDGS search best-effort contract ---
def test_ddgs_search_swallows_exceptions(monkeypatch):
    class _BoomDDGS:
        def __init__(self, *a, **k):
            pass

        def text(self, *a, **k):
            raise RuntimeError("rate limited")

    fake = types.ModuleType("ddgs")
    fake.DDGS = _BoomDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake)
    assert _ddgs.search("anything", site="reddit.com") == []


def test_ddgs_search_scopes_query_to_site(monkeypatch):
    captured = {}

    class _FakeDDGS:
        def __init__(self, *a, **k):
            pass

        def text(self, query, **k):
            captured["query"] = query
            captured["max_results"] = k.get("max_results")
            return [{"title": "t", "href": "https://reddit.com/x", "body": "snippet text"}]

    fake = types.ModuleType("ddgs")
    fake.DDGS = _FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake)
    out = _ddgs.search("noise cancelling", site="reddit.com", max_results=7)
    assert captured["query"] == "site:reddit.com noise cancelling"
    assert captured["max_results"] == 7
    assert out and out[0]["body"] == "snippet text"


# --- per-platform fetch wrappers ---
def _fake_search(monkeypatch, capture):
    def fake(query, *, site=None, max_results=None):
        capture.append({"query": query, "site": site, "max_results": max_results})
        return [
            {"title": f"t{i}", "href": f"https://h/{i}", "body": f"body {i}"} for i in range(25)
        ]

    monkeypatch.setattr(_ddgs, "search", fake)


def test_each_fetch_scopes_to_its_domain(monkeypatch):
    cases = [
        (youtube, "youtube.com", "youtube"),
        (reddit, "reddit.com", "reddit"),
        (tiktok, "tiktok.com", "tiktok"),
        (instagram, "instagram.com", "instagram"),
    ]
    for module, site, source in cases:
        cap = []
        _fake_search(monkeypatch, cap)
        out = list(module.fetch("xm5", limit=5))
        assert cap[0]["site"] == site
        assert len(out) == 5  # respects limit
        assert all(c.source == source for c in out)


def test_x_fetch_covers_both_domains(monkeypatch):
    cap = []
    _fake_search(monkeypatch, cap)
    out = list(x.fetch("xm5", limit=3))
    assert cap[0]["site"] is None  # scope baked into the query
    assert "site:x.com" in cap[0]["query"] and "site:twitter.com" in cap[0]["query"]
    assert len(out) == 3 and all(c.source == "x" for c in out)


def test_fetch_returns_empty_when_search_dry(monkeypatch):
    monkeypatch.setattr(_ddgs, "search", lambda *a, **k: [])
    assert list(youtube.fetch("xm5")) == []


# --- pure helper (scrape/_util.py) ---
def test_stable_id_is_deterministic():
    assert stable_id("a", "b") == stable_id("a", "b")
    assert stable_id("a", "b") != stable_id("a", "c")
