"""Routes LLM chat calls to the right provider based on model prefix.

Conventions:
  - ``openai/<model>``    -> OpenAI Chat Completions
  - ``anthropic/<model>`` -> Anthropic Messages
  - anything else         -> Ollama (local)

Same ``chat()`` and ``health()`` shape as ``OllamaClient`` so anything that
held an ``OllamaClient`` (e.g. ``ExtractorWorker``) can hold an ``LLMRouter``
instead with no other changes.
"""

from __future__ import annotations

from typing import Literal

from backend.anthropic_client import AnthropicClient
from backend.ollama_client import OllamaClient
from backend.openai_client import OpenAIClient

HealthStatus = Literal["ok", "no_model", "offline"]

OPENAI_PREFIX = "openai/"
ANTHROPIC_PREFIX = "anthropic/"


def provider_of(model: str) -> str:
    if model.startswith(OPENAI_PREFIX):
        return "openai"
    if model.startswith(ANTHROPIC_PREFIX):
        return "anthropic"
    return "ollama"


def strip_prefix(model: str) -> str:
    for p in (OPENAI_PREFIX, ANTHROPIC_PREFIX):
        if model.startswith(p):
            return model[len(p):]
    return model


class LLMRouter:
    def __init__(
        self,
        *,
        ollama_url: str = "http://localhost:11434",
        openai_key: str = "",
        anthropic_key: str = "",
    ) -> None:
        self._ollama = OllamaClient(base_url=ollama_url)
        self._openai_key = openai_key
        self._anthropic_key = anthropic_key

    def set_openai_key(self, key: str) -> None:
        self._openai_key = key.strip()

    def set_anthropic_key(self, key: str) -> None:
        self._anthropic_key = key.strip()

    @property
    def openai_set(self) -> bool:
        return bool(self._openai_key)

    @property
    def anthropic_set(self) -> bool:
        return bool(self._anthropic_key)

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        format: str | None = "json",
        temperature: float = 0.2,
        timeout_s: float = 180.0,
    ) -> str:
        provider = provider_of(model)
        bare = strip_prefix(model)
        if provider == "openai":
            if not self._openai_key:
                raise RuntimeError("OpenAI API key not set")
            client = OpenAIClient(api_key=self._openai_key)
            return await client.chat(
                messages=messages, model=bare,
                format=format, temperature=temperature, timeout_s=min(timeout_s, 60.0),
            )
        if provider == "anthropic":
            if not self._anthropic_key:
                raise RuntimeError("Anthropic API key not set")
            client = AnthropicClient(api_key=self._anthropic_key)
            return await client.chat(
                messages=messages, model=bare,
                format=format, temperature=temperature, timeout_s=min(timeout_s, 60.0),
            )
        return await self._ollama.chat(
            messages=messages, model=bare,
            format=format, temperature=temperature, timeout_s=timeout_s,
        )

    async def health(self, *, model: str, timeout_s: float = 5.0) -> HealthStatus:
        provider = provider_of(model)
        bare = strip_prefix(model)
        if provider == "openai":
            if not self._openai_key:
                return "no_model"
            return await OpenAIClient(api_key=self._openai_key).health(model=bare, timeout_s=timeout_s)
        if provider == "anthropic":
            if not self._anthropic_key:
                return "no_model"
            return await AnthropicClient(api_key=self._anthropic_key).health(model=bare, timeout_s=timeout_s)
        return await self._ollama.health(model=bare, timeout_s=timeout_s)
