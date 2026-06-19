from voc_analyzer import config


def test_env_int_reads_valid_value(monkeypatch):
    monkeypatch.setenv("VOC_TEST_INT", "7")
    assert config._env_int("VOC_TEST_INT", 3) == 7


def test_env_int_missing_or_blank_uses_default(monkeypatch):
    monkeypatch.delenv("VOC_TEST_INT", raising=False)
    assert config._env_int("VOC_TEST_INT", 3) == 3
    monkeypatch.setenv("VOC_TEST_INT", "  ")
    assert config._env_int("VOC_TEST_INT", 3) == 3


def test_env_int_warns_and_defaults_on_invalid(monkeypatch, caplog):
    monkeypatch.setenv("VOC_TEST_INT", "not-a-number")
    with caplog.at_level("WARNING"):
        assert config._env_int("VOC_TEST_INT", 3) == 3
    assert "VOC_TEST_INT" in caplog.text


def test_llm_api_key_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("VOC_LLM_API_KEY", "explicit")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic")
    monkeypatch.setenv("VOC_LLM_PROVIDER", "openai")
    assert config.llm_api_key() == "explicit"


def test_llm_api_key_falls_back_per_provider(monkeypatch):
    monkeypatch.delenv("VOC_LLM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    monkeypatch.setenv("VOC_LLM_PROVIDER", "anthropic")
    assert config.llm_api_key() == "ak"
    monkeypatch.setenv("VOC_LLM_PROVIDER", "openai")
    assert config.llm_api_key() == "ok"


def test_llm_enabled_reflects_key_presence(monkeypatch):
    monkeypatch.delenv("VOC_LLM_API_KEY", raising=False)
    monkeypatch.setenv("VOC_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert config.llm_enabled() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    assert config.llm_enabled() is True


def test_llm_enabled_openai_true_without_key(monkeypatch):
    # OpenAI-compatible endpoints (e.g. a local Ollama/vLLM server) don't require a key.
    monkeypatch.delenv("VOC_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VOC_LLM_PROVIDER", "openai")
    assert config.llm_enabled() is True


def test_anthropic_enabled_is_alias(monkeypatch):
    # Back-compat alias must point at the same callable.
    assert config.anthropic_enabled is config.llm_enabled
