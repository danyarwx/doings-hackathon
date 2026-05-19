"""Async worker that extracts requirements from the rolling transcript window."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.extractor_filter import FilterConfig, filter_candidates
from backend.extractor_prompt import build_messages
from backend.insights import Insight
from backend.ollama_client import OllamaClient
from backend.state import Segment, SessionState

DEFAULT_TICK_S = 5.0
DEFAULT_WINDOW_S = 30.0


def build_window(segments: list[Segment], window_s: float) -> list[Segment]:
    if not segments:
        return []
    cutoff = max(0.0, segments[-1].end_s - window_s)
    return [s for s in segments if s.end_s >= cutoff]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractorWorker:
    def __init__(
        self,
        *,
        state: SessionState,
        hub: Any,
        client: OllamaClient,
        model: str,
        tick_s: float = DEFAULT_TICK_S,
        window_s: float = DEFAULT_WINDOW_S,
    ) -> None:
        self._state = state
        self._hub = hub
        self._client = client
        self._model = model
        self._tick_s = tick_s
        self._window_s = window_s
        self._cfg = FilterConfig()
        self._in_flight = False
        self._counter = 0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._tick_s)
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[extractor] tick error: {exc}", file=sys.stderr)

    async def _tick_once(self) -> None:
        if self._state.recording_state != "recording":
            return
        if self._in_flight:
            return
        window = build_window(self._state.segments, self._window_s)
        if not window:
            return

        self._in_flight = True
        try:
            existing_texts = [
                ins.text for ins in self._state.insights if ins.status != "declined"
            ][-10:]
            messages = build_messages(window=window, existing_texts=existing_texts)
            try:
                raw = await self._client.chat(messages=messages, model=self._model)
            except httpx.HTTPError as exc:
                await self._hub.broadcast({
                    "type": "ai_status",
                    "state": "offline",
                    "model": self._model,
                    "error": str(exc),
                })
                return

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[extractor] non-json reply: {exc}; raw={raw[:200]!r}", file=sys.stderr)
                return

            candidates = data.get("requirements", []) or []
            if not isinstance(candidates, list):
                return

            result = filter_candidates(
                candidates,
                window=window,
                existing_texts=existing_texts,
                cfg=self._cfg,
            )

            for d in result.dropped:
                print(f"[extractor] dropped ({d.gate}): {d.reason}", file=sys.stderr)

            for cand in result.kept:
                self._counter += 1
                ins = Insight(
                    id=f"ins-{self._counter:03d}",
                    session_id=self._state.session_id or "sess-unknown",
                    category=cand["category"],
                    text=cand["text"],
                    original_text=cand["text"],
                    source_quote=str(cand.get("source_quote", "")),
                    language=str(cand.get("language", "en")),
                    confidence=float(cand.get("confidence", 0.0)),
                    status="pending",
                    created_at_iso=_iso_now(),
                )
                self._state.insights.append(ins)
                await self._hub.broadcast({"type": "insight", "insight": _insight_to_dict(ins)})

            await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
        finally:
            self._in_flight = False


def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "confidence": ins.confidence,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }
