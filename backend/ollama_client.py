"""Async wrapper around Ollama's HTTP API."""

from __future__ import annotations

from typing import Literal

import httpx

HealthStatus = Literal["ok", "no_model", "offline"]


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        format: str | None = "json",
        temperature: float = 0.2,
        timeout_s: float = 180.0,
    ) -> str:
        """Call POST /api/chat and return the assistant's content string."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format is not None:
            payload["format"] = format
        async with httpx.AsyncClient(timeout=timeout_s) as http:
            r = await http.post(f"{self._base}/api/chat", json=payload)
            r.raise_for_status()
            body = r.json()
        return body["message"]["content"]

    async def health(self, *, model: str, timeout_s: float = 2.0) -> HealthStatus:
        """Probe Ollama and check the named model is installed.

        Accepts both stem-only (`phi3`) and stem:tag (`qwen3:8b`) model ids.
        Ollama stores entries with explicit tags (e.g. `qwen3:8b`, `phi3:latest`).
        We match if either the full id matches verbatim, or the stem alone matches.
        """
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                r = await http.get(f"{self._base}/api/tags")
            if r.status_code != 200:
                return "offline"
            installed = {m.get("name", "") for m in r.json().get("models", [])}
            installed_stems = {n.split(":", 1)[0] for n in installed}
            if ":" in model:
                # Caller asked for an explicit tag — only an exact match counts.
                return "ok" if model in installed else "no_model"
            # Caller asked for a stem — any tag of that stem counts.
            return "ok" if model in installed_stems else "no_model"
        except httpx.HTTPError:
            return "offline"
