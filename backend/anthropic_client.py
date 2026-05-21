"""Anthropic Messages API client (x-api-key auth).

Conforms to the same chat()/health() shape as OllamaClient so the
LLMRouter can swap it in transparently. Anthropic puts the system
prompt at top-level; we extract it from the messages list.
"""

from __future__ import annotations

from typing import Literal

import httpx

HealthStatus = Literal["ok", "no_model", "offline"]


class AnthropicClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com/v1") -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        format: str | None = "json",
        temperature: float = 0.2,
        timeout_s: float = 60.0,
        max_tokens: int = 1024,
    ) -> str:
        # Anthropic puts the system prompt at top-level, not inside messages.
        system_msg = ""
        chat_msgs: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = (system_msg + "\n" + m["content"]).strip() if system_msg else m["content"]
            else:
                chat_msgs.append({"role": m["role"], "content": m["content"]})
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_msgs,
        }
        if system_msg:
            payload["system"] = system_msg
        headers = {
            "x-api-key": self._key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout_s) as http:
            r = await http.post(f"{self._base}/messages", json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
        # Concatenate text blocks from the content array.
        parts = [b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"]
        return "".join(parts)

    async def health(self, *, model: str, timeout_s: float = 8.0) -> HealthStatus:
        if not self._key:
            return "offline"
        # No cheap list-models endpoint on Anthropic; do a 1-token probe.
        try:
            headers = {
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            }
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                r = await http.post(f"{self._base}/messages", json=payload, headers=headers)
            if r.status_code == 401 or r.status_code == 403:
                return "offline"
            if r.status_code == 404:
                return "no_model"
            if r.status_code != 200:
                return "offline"
            return "ok"
        except httpx.HTTPError:
            return "offline"
