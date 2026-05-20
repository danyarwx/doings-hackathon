"""Event-driven worker that extracts requirements from utterances.

Consumes Utterances from a SentenceBuffer's queue. For each utterance, builds
a FOCUS+CONTEXT prompt, calls the LLM, filters candidates, and broadcasts
surviving Insights.

Skip-if-busy: if an LLM call is in flight when a new utterance arrives, the
new one is dropped (fresh signals matter more than catching every utterance).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.extractor_filter import FilterConfig, filter_candidates
from backend.extractor_prompt import CONTEXT_TAIL, build_messages
from backend.insights import Insight
from backend.ollama_client import OllamaClient
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import SessionState


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
        buffer: SentenceBuffer,
    ) -> None:
        self._state = state
        self._hub = hub
        self._client = client
        self._model = model
        self._buffer = buffer
        self._cfg = FilterConfig()
        self._in_flight = False
        self._counter = 0
        self._task: asyncio.Task | None = None
        self._context: deque[Utterance] = deque(maxlen=CONTEXT_TAIL)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    def set_model(self, model: str) -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

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
            try:
                u = await self._buffer.queue.get()
                await self._handle(u)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[extractor] error: {exc}", file=sys.stderr)

    async def _handle(self, focus: Utterance) -> None:
        if self._state.recording_state != "recording":
            # Still update context so a resumed session has continuity.
            self._context.append(focus)
            return
        if self._in_flight:
            print(
                f"[extractor] skip-if-busy: dropping utterance ({len(focus.text)} chars)",
                file=sys.stderr,
            )
            self._context.append(focus)
            return

        self._in_flight = True
        t0 = time.monotonic()
        preview = focus.text[:80] + ("…" if len(focus.text) > 80 else "")
        print(f"[extractor] -> {self._model}: {preview!r}", file=sys.stderr)
        await self._hub.broadcast({
            "type": "ai_status",
            "state": "thinking",
            "model": self._model,
        })
        try:
            existing_texts = [
                ins.text for ins in self._state.insights if ins.status != "declined"
            ][-10:]
            messages = build_messages(
                focus=focus,
                context=list(self._context),
                existing_texts=existing_texts,
            )
            try:
                raw = await self._client.chat(messages=messages, model=self._model)
            except httpx.HTTPError as exc:
                elapsed = time.monotonic() - t0
                print(
                    f"[extractor] LLM call failed after {elapsed:.1f}s: {exc}",
                    file=sys.stderr,
                )
                await self._hub.broadcast({
                    "type": "ai_status",
                    "state": "offline",
                    "model": self._model,
                    "error": str(exc),
                })
                return

            elapsed = time.monotonic() - t0
            print(
                f"[extractor] <- {self._model}: {elapsed:.1f}s, {len(raw)} chars",
                file=sys.stderr,
            )

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"[extractor] non-json reply: {exc}; raw={raw[:300]!r}",
                    file=sys.stderr,
                )
                await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
                return

            candidates = data.get("requirements", []) or []
            if not isinstance(candidates, list):
                print(f"[extractor] 'requirements' was not a list: {type(candidates)}", file=sys.stderr)
                await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
                return

            print(
                f"[extractor] {self._model} returned {len(candidates)} candidates",
                file=sys.stderr,
            )

            result = filter_candidates(
                candidates,
                focus=focus,
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
                    certainty=cand["certainty"],
                    text=cand["text"],
                    original_text=cand["text"],
                    source_quote=str(cand.get("source_quote", "")),
                    language=str(cand.get("language", "en")),
                    status="pending",
                    created_at_iso=_iso_now(),
                )
                self._state.insights.append(ins)
                await self._hub.broadcast({"type": "insight", "insight": _insight_to_dict(ins)})

            print(
                f"[extractor] kept {len(result.kept)} / dropped {len(result.dropped)}",
                file=sys.stderr,
            )
            await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
        finally:
            self._in_flight = False
            self._context.append(focus)


def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "certainty": ins.certainty,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }
