import sys
import types

import pytest

from voc_analyzer import config, llm


# --- anthropic branch (fake SDK injected into sys.modules) ---
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


def test_complete_anthropic_branch(monkeypatch):
    monkeypatch.setenv("VOC_LLM_PROVIDER", "anthropic")
    captured = _install_fake_anthropic(monkeypatch, "hello from claude")
    out = llm.complete("SYS", "USR", model="claude-sonnet-4-6", max_tokens=128)
    assert out == "hello from claude"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["max_tokens"] == 128
    # system is a cacheable block; single user turn
    assert captured["system"][0]["text"] == "SYS"
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["messages"] == [{"role": "user", "content": "USR"}]


# --- openai-compatible branch (httpx.post monkeypatched) ---
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_complete_openai_branch(monkeypatch):
    monkeypatch.setenv("VOC_LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(config, "llm_api_key", lambda: "free-key")
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return _FakeResponse({"choices": [{"message": {"content": "hi from qwen"}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete("SYS", "USR", model="qwen-2.5", max_tokens=64)
    assert out == "hi from qwen"
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer free-key"
    assert captured["json"]["model"] == "qwen-2.5"
    assert captured["json"]["max_tokens"] == 64
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]


def test_complete_openai_without_key_omits_auth_header(monkeypatch):
    monkeypatch.setenv("VOC_LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "llm_api_key", lambda: None)
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["headers"] = headers
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.complete("S", "U", model="m", max_tokens=8) == "ok"
    assert "Authorization" not in captured["headers"]


def test_complete_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("VOC_LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        llm.complete("S", "U", model="m", max_tokens=8)
