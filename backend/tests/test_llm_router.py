"""Tests for LLMRouter dispatch + key handling."""

import pytest

from backend.llm_router import LLMRouter, provider_of, strip_prefix


def test_provider_of_recognizes_prefixes():
    assert provider_of("openai/gpt-4o-mini") == "openai"
    assert provider_of("anthropic/claude-haiku-4-5") == "anthropic"
    assert provider_of("phi3") == "ollama"
    assert provider_of("qwen3:8b") == "ollama"


def test_strip_prefix_only_strips_provider():
    assert strip_prefix("openai/gpt-4o-mini") == "gpt-4o-mini"
    assert strip_prefix("anthropic/claude-haiku-4-5") == "claude-haiku-4-5"
    # Ollama tags with ":" should NOT be touched.
    assert strip_prefix("qwen3:8b") == "qwen3:8b"
    assert strip_prefix("phi4-mini:3.8b") == "phi4-mini:3.8b"
    assert strip_prefix("phi3") == "phi3"


def test_router_key_flags_track_setters():
    r = LLMRouter()
    assert not r.openai_set
    assert not r.anthropic_set
    r.set_openai_key("sk-test")
    r.set_anthropic_key("sk-ant-test")
    assert r.openai_set
    assert r.anthropic_set
    r.set_openai_key("")
    assert not r.openai_set
    assert r.anthropic_set


def test_router_set_key_strips_whitespace():
    r = LLMRouter()
    r.set_openai_key("  sk-test  \n")
    assert r.openai_set


@pytest.mark.asyncio
async def test_chat_raises_when_cloud_key_missing():
    r = LLMRouter()
    with pytest.raises(RuntimeError, match="OpenAI"):
        await r.chat(messages=[{"role": "user", "content": "hi"}], model="openai/gpt-4o-mini")
    with pytest.raises(RuntimeError, match="Anthropic"):
        await r.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.asyncio
async def test_health_returns_no_model_when_cloud_key_missing():
    r = LLMRouter()
    assert await r.health(model="openai/gpt-4o-mini") == "no_model"
    assert await r.health(model="anthropic/claude-haiku-4-5") == "no_model"
