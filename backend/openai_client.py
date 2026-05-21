"""OpenAI Chat Completions client (Bearer auth).

Conforms to the same chat()/health() shape as OllamaClient so the
LLMRouter can swap it in transparently.
"""

from __future__ import annotations

from typing import Literal

import httpx

HealthStatus = Literal["ok", "no_model", "offline"]


class OpenAIClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
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
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if format == "json":
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=timeout_s) as http:
            r = await http.post(f"{self._base}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
        return body["choices"][0]["message"]["content"]

    async def health(self, *, model: str, timeout_s: float = 5.0) -> HealthStatus:
        if not self._key:
            return "offline"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                r = await http.get(
                    f"{self._base}/models",
                    headers={"Authorization": f"Bearer {self._key}"},
                )
            if r.status_code == 401:
                return "offline"
            if r.status_code != 200:
                return "offline"
            return "ok"
        except httpx.HTTPError:
            return "offline"
