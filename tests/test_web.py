import json

import pytest
from fastapi.testclient import TestClient

from voc_analyzer.scrape import FETCHERS
from voc_analyzer.web.api import app

client = TestClient(app)

# Every test uses the offline demo path (demo=True, use_llm=False): no network, no DDGS, no LLM.
ANALYSIS_KEYS = {
    "product", "keywords", "platforms", "generated_at", "totals", "sentiment",
    "top_keywords", "top_phrases", "keywords_by_sentiment", "trends",
    "representative", "summary", "suggestions",
}


def _run_demo(product="Acme Buds", use_llm=False, **extra):
    """Create a demo job and drain its SSE stream to completion; return (job_id, events)."""
    resp = client.post(
        "/api/analyses", json={"product": product, "demo": True, "use_llm": use_llm, **extra}
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    events = []
    with client.stream("GET", f"/api/analyses/{job_id}/progress") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return job_id, events


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"]


def test_meta():
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert set(body["platforms"]) == set(FETCHERS)
    assert isinstance(body["llm_enabled"], bool)
    assert "max_rounds" in body["gather_defaults"]
    assert isinstance(body["models"], list) and body["models"]
    assert body["default_model"] in body["models"]


def test_models_endpoint(monkeypatch):
    from voc_analyzer import config

    monkeypatch.setattr(config, "llm_available_models", lambda: ["x/one", "y/two"])
    r = client.get("/api/models")
    assert r.status_code == 200
    assert r.json()["models"] == ["x/one", "y/two"]


def test_create_accepts_model_override():
    r = client.post(
        "/api/analyses",
        json={"product": "Acme", "demo": True, "use_llm": False, "model": "qwen/some-model"},
    )
    assert r.status_code == 202


def test_create_streams_progress_then_done():
    _, events = _run_demo()
    assert any(e["type"] == "progress" for e in events)  # the "loaded N comments" line
    assert events[-1]["type"] == "done"
    assert not any(e["type"] == "error" for e in events)


def test_result_has_analysis_shape():
    job_id, _ = _run_demo()
    r = client.get(f"/api/analyses/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["comment_count"] == 11  # sample comments.jsonl line count
    result = body["result"]
    assert set(result) >= ANALYSIS_KEYS
    assert result["totals"]["comments"] == 11
    assert result["summary"] == ""  # use_llm=False → no narrative summary
    assert isinstance(result["suggestions"], list) and result["suggestions"]  # rule-based


def test_download_report_md():
    job_id, _ = _run_demo(product="Acme Buds")
    r = client.get(f"/api/analyses/{job_id}/report.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "# Voice of Customer" in r.text and "Acme Buds" in r.text


def test_download_analysis_json_matches_result():
    job_id, _ = _run_demo()
    status = client.get(f"/api/analyses/{job_id}").json()["result"]
    dl = client.get(f"/api/analyses/{job_id}/analysis.json")
    assert dl.status_code == 200
    assert json.loads(dl.text) == status


def test_unknown_platform_rejected():
    r = client.post("/api/analyses", json={"product": "X", "platforms": ["myspace"]})
    assert r.status_code == 422


def test_empty_product_rejected():
    assert client.post("/api/analyses", json={"product": ""}).status_code == 422
    assert client.post("/api/analyses", json={"product": "   "}).status_code == 422


def test_unknown_job_404():
    assert client.get("/api/analyses/nope").status_code == 404
    assert client.get("/api/analyses/nope/report.md").status_code == 404
    assert client.get("/api/analyses/nope/analysis.json").status_code == 404


def test_download_before_done_is_409_or_done():
    # Race-tolerant: the demo job may already be finished when we ask.
    job_id = client.post(
        "/api/analyses", json={"product": "Acme", "demo": True, "use_llm": False}
    ).json()["job_id"]
    r = client.get(f"/api/analyses/{job_id}/report.md")
    assert r.status_code in (200, 409)


def test_job_error_path(monkeypatch):
    from voc_analyzer import _pipeline

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(_pipeline, "run_analysis", boom)
    job_id, events = _run_demo(product="Acme")
    assert events[-1] == {"type": "error", "error": "kaboom"}
    status = client.get(f"/api/analyses/{job_id}").json()
    assert status["status"] == "error" and status["error"] == "kaboom"


@pytest.mark.parametrize("path", ["", "report.md", "analysis.json"])
def test_progress_and_downloads_404_for_unknown(path):
    suffix = f"/{path}" if path else ""
    assert client.get(f"/api/analyses/missing{suffix}").status_code == 404
