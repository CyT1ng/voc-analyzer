"""Provider-agnostic LLM completion — one call site for every model backend.

The analyzer's LLM features (gather agent, report suggestions/summary) all route
through ``complete``. The default provider is Anthropic; setting ``VOC_LLM_PROVIDER=openai``
(plus ``VOC_LLM_BASE_URL`` / ``VOC_LLM_API_KEY``) points them at any OpenAI-compatible
``/chat/completions`` endpoint — which is how free models such as Qwen are reached via
OpenRouter, DashScope, a local Ollama/vLLM server, etc.

``complete`` raises on any error; callers (``report/suggest.py``, ``gather/agent.py``)
own the graceful fallback (rule-based suggestions / deterministic gather decision).
"""

from __future__ import annotations

import logging

import httpx

from voc_analyzer import config

log = logging.getLogger(__name__)
_warned_models: set[str] = set()


def complete(system: str, user: str, *, model: str, max_tokens: int) -> str:
    """Run a single non-streaming completion and return the response text.

    Dispatches on ``config.llm_provider()``. Raises on transport/parse errors.
    """
    provider = config.llm_provider()
    if provider == "anthropic":
        return _anthropic(system, user, model=model, max_tokens=max_tokens)
    if provider == "openai":
        _warn_if_model_mismatch(model)
        return _openai_compatible(system, user, model=model, max_tokens=max_tokens)
    raise ValueError(f"unknown VOC_LLM_PROVIDER: {provider!r} (expected 'anthropic' or 'openai')")


def _warn_if_model_mismatch(model: str) -> None:
    """Catch the easy footgun: provider=openai but the model id is still an Anthropic default."""
    if model.startswith("claude-") and model not in _warned_models:
        _warned_models.add(model)
        log.warning(
            "VOC_LLM_PROVIDER=openai but model id %r looks like an Anthropic id; set "
            "VOC_LLM_MODEL / VOC_AGENT_MODEL to the provider's model id (e.g. a Qwen id)",
            model,
        )


def _anthropic(system: str, user: str, *, model: str, max_tokens: int) -> str:
    """Anthropic Messages API (system as a cacheable block, single user turn)."""
    from anthropic import Anthropic

    client = Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text")


def _openai_compatible(system: str, user: str, *, model: str, max_tokens: int) -> str:
    """OpenAI-compatible ``/chat/completions`` (free Qwen via OpenRouter/DashScope/Ollama/…)."""
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = config.llm_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=config.LLM_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
