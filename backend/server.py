"""FastAPI fan-out: receives segments, broadcasts to UI, posts to staging."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.delivery import deliver
from backend.extractor import ExtractorWorker
from backend.insights import Insight
from backend.llm_router import LLMRouter, provider_of
from backend.sentence_buffer import SentenceBuffer
from backend.state import Segment, SessionState

DEFAULT_ENDPOINT = "https://staging.doings.de/stt"
DEFAULT_MODEL = "phi3"

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPTURE_PYTHON = REPO_ROOT / "capture" / ".venv" / "bin" / "python"
DEFAULT_CAPTURE_CMD = (
    f"{CAPTURE_PYTHON} -m capture.main --api-url http://localhost:8000"
)


class SegmentIn(BaseModel):
    id: str
    session_id: str
    text: str
    start_s: float
    end_s: float
    lang: str


class Hub:
    """Tracks connected WS clients and broadcasts JSON messages."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = SessionState()
    app.state.hub = Hub()
    app.state.endpoint = os.getenv("DOINGS_ENDPOINT", DEFAULT_ENDPOINT)
    app.state.capture_proc = None
    # In-memory list of finished sessions (PRD forbids persistence).
    app.state.past_sessions = []
    # Whisper prompt hint set from the UI; applied on next /control/start.
    app.state.vocabulary = ""

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    app.state.ollama_model = model
    app.state.llm = LLMRouter(
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        openai_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", ""),
    )
    app.state.sentence_buffer = SentenceBuffer()
    app.state.extractor = ExtractorWorker(
        state=app.state.session,
        hub=app.state.hub,
        client=app.state.llm,
        model=model,
        buffer=app.state.sentence_buffer,
    )
    app.state.extractor.start()

    yield

    await app.state.extractor.stop()
    proc = app.state.capture_proc
    if proc is not None and proc.returncode is None:
        proc.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()


app = FastAPI(lifespan=lifespan)


def _segment_to_dict(seg: Segment) -> dict:
    return {
        "id": seg.id,
        "session_id": seg.session_id,
        "text": seg.text,
        "start_s": seg.start_s,
        "end_s": seg.end_s,
        "lang": seg.lang,
    }


def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "detail": ins.detail,
        "language": ins.language,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }


def _find_insight(app: FastAPI, ins_id: str) -> tuple[int, Insight] | None:
    for i, ins in enumerate(app.state.session.insights):
        if ins.id == ins_id:
            return i, ins
    return None


def _replace_insight(app: FastAPI, idx: int, new: Insight) -> None:
    app.state.session.insights[idx] = new


async def _deliver_and_report(seg: Segment) -> None:
    payload = {
        "text": seg.text,
        "start_ms": int(seg.start_s * 1000),
        "end_ms": int(seg.end_s * 1000),
        "lang": seg.lang,
        "session_id": seg.session_id,
    }
    await app.state.hub.broadcast({
        "type": "delivery",
        "id": seg.id,
        "status": "pending",
        "attempts": 0,
    })
    result = await deliver(payload=payload, endpoint=app.state.endpoint)
    app.state.session.update_delivery(seg.id, status=result.status, attempts=result.attempts)
    await app.state.hub.broadcast({
        "type": "delivery",
        "id": seg.id,
        "status": result.status,
        "attempts": result.attempts,
    })


def _capture_command(language: str | None = None, vocabulary: str | None = None) -> list[str]:
    cmd_str = os.getenv("CAPTURE_CMD", DEFAULT_CAPTURE_CMD)
    parts = shlex.split(cmd_str)
    if language and "--language" not in parts:
        parts += ["--language", language]
    if vocabulary and vocabulary.strip() and "--prompt" not in parts:
        parts += ["--prompt", vocabulary.strip()]
    return parts


def _capture_env(session_id: str) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["CAPTURE_SESSION_ID"] = session_id
    return env


def _new_session_id() -> str:
    from datetime import datetime
    return "sess-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _archive_current_session(app: FastAPI) -> None:
    s: SessionState = app.state.session
    if s.session_id is None or not s.segments:
        return
    languages = sorted({seg.lang for seg in s.segments})
    duration_s = (s.segments[-1].end_s - s.segments[0].start_s) if s.segments else 0.0
    snapshot = {
        "session_id": s.session_id,
        "ended_at_iso": _utc_iso_now(),
        "segment_count": len(s.segments),
        "duration_s": round(duration_s, 1),
        "languages": languages,
        "segments": [_segment_to_dict(seg) for seg in s.segments],
    }
    app.state.past_sessions.insert(0, snapshot)  # newest first


def _utc_iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _monitor_capture(app: FastAPI) -> None:
    proc = app.state.capture_proc
    if proc is None:
        return
    await proc.wait()
    # If the subprocess died while we were already transitioning (pause/stop),
    # those routes set the authoritative state — don't overwrite it here.
    if app.state.session.recording_state == "recording":
        app.state.capture_proc = None
        app.state.session.recording_state = "idle"
        await app.state.hub.broadcast({
            "type": "state",
            "state": "idle",
            "session_id": app.state.session.session_id,
        })


class StartBody(BaseModel):
    language: str | None = None


@app.post("/control/start")
async def control_start(body: StartBody | None = None) -> dict:
    if (
        app.state.session.recording_state == "recording"
        or (app.state.capture_proc is not None and app.state.capture_proc.returncode is None)
    ):
        raise HTTPException(status_code=409, detail="already recording")

    language = body.language if body else None
    resuming_from_paused = app.state.session.recording_state == "paused"
    if not resuming_from_paused:
        # Archive the just-finished session before wiping it.
        _archive_current_session(app)
        # Fresh session: clear segments + delivery state, mint a new id.
        app.state.session.reset(session_id=_new_session_id())
        app.state.sentence_buffer.reset()

    session_id = app.state.session.session_id or _new_session_id()
    if app.state.session.session_id is None:
        app.state.session.session_id = session_id

    cmd = _capture_command(language=language, vocabulary=app.state.vocabulary)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=str(REPO_ROOT),
        env=_capture_env(session_id),
    )
    app.state.capture_proc = proc
    app.state.session.recording_state = "recording"
    asyncio.create_task(_monitor_capture(app))
    await app.state.hub.broadcast({
        "type": "state",
        "state": "recording",
        "session_id": session_id,
    })
    return {"pid": proc.pid, "session_id": session_id}


@app.post("/control/pause")
async def control_pause() -> dict:
    proc = app.state.capture_proc
    if proc is None or proc.returncode is not None or app.state.session.recording_state != "recording":
        raise HTTPException(status_code=409, detail="not recording")
    app.state.session.recording_state = "paused"
    proc.send_signal(signal.SIGINT)
    try:
        await asyncio.wait_for(proc.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    app.state.capture_proc = None
    # Flush any pending segments so the LLM still sees the trailing speech.
    await app.state.sentence_buffer.flush_pending()
    await app.state.hub.broadcast({
        "type": "state",
        "state": "paused",
        "session_id": app.state.session.session_id,
    })
    return {"paused": True}


@app.post("/control/stop")
async def control_stop() -> dict:
    state = app.state.session.recording_state
    proc = app.state.capture_proc
    # Stop is valid from both recording and paused.
    if state == "idle":
        raise HTTPException(status_code=409, detail="not recording")
    app.state.session.recording_state = "stopping"
    await app.state.hub.broadcast({
        "type": "state",
        "state": "stopping",
        "session_id": app.state.session.session_id,
    })
    if proc is not None and proc.returncode is None:
        proc.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    app.state.capture_proc = None
    # Flush any pending segments so the LLM still sees the trailing speech
    # from the just-ended session.
    await app.state.sentence_buffer.flush_pending()
    app.state.session.recording_state = "idle"
    await app.state.hub.broadcast({
        "type": "state",
        "state": "idle",
        "session_id": app.state.session.session_id,
    })
    return {"stopped": True}


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/state")
async def get_state() -> dict:
    s: SessionState = app.state.session
    return {
        "state": s.recording_state,
        "session_id": s.session_id,
        "segment_count": len(s.segments),
        "delivered_count": s.delivered_count(),
    }


@app.get("/session/export")
async def export_session() -> dict:
    s: SessionState = app.state.session
    return {
        "session_id": s.session_id,
        "segments": [_segment_to_dict(seg) for seg in s.segments],
    }


@app.get("/history")
async def list_history() -> dict:
    return {
        "sessions": [
            {
                "session_id": h["session_id"],
                "ended_at_iso": h["ended_at_iso"],
                "segment_count": h["segment_count"],
                "duration_s": h["duration_s"],
                "languages": h["languages"],
            }
            for h in app.state.past_sessions
        ],
    }


@app.get("/history/{session_id}")
async def get_history_session(session_id: str) -> dict:
    for h in app.state.past_sessions:
        if h["session_id"] == session_id:
            return {
                "session_id": h["session_id"],
                "ended_at_iso": h["ended_at_iso"],
                "segments": h["segments"],
            }
    raise HTTPException(status_code=404, detail="session not found")


@app.post("/segments", status_code=202)
async def post_segment(payload: SegmentIn) -> dict:
    seg = Segment(
        id=payload.id,
        session_id=payload.session_id,
        text=payload.text,
        start_s=payload.start_s,
        end_s=payload.end_s,
        lang=payload.lang,
    )
    app.state.session.add_segment(seg)
    await app.state.sentence_buffer.add(seg)
    await app.state.hub.broadcast({"type": "segment", "segment": _segment_to_dict(seg)})
    asyncio.create_task(_deliver_and_report(seg))
    return {"accepted": True}


class EditBody(BaseModel):
    text: str


@app.get("/insights")
async def list_insights() -> dict:
    return {"insights": [_insight_to_dict(i) for i in app.state.session.insights]}


@app.post("/insights/{ins_id}/approve")
async def approve_insight(ins_id: str) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    from dataclasses import replace
    new = replace(ins, status="approved")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.post("/insights/{ins_id}/decline")
async def decline_insight(ins_id: str) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    from dataclasses import replace
    new = replace(ins, status="declined")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.post("/insights/{ins_id}/edit")
async def edit_insight(ins_id: str, body: EditBody) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    new_text = body.text.strip()
    if not new_text or len(new_text) > 500:
        raise HTTPException(status_code=400, detail="text must be 1..500 chars")
    from dataclasses import replace
    new = replace(ins, text=new_text, status="pending")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.get("/ai/status")
async def ai_status() -> dict:
    result = await app.state.llm.health(model=app.state.ollama_model)
    return {"state": result, "model": app.state.ollama_model}


class VocabularyBody(BaseModel):
    text: str


@app.get("/vocabulary")
async def get_vocabulary() -> dict:
    return {"text": app.state.vocabulary}


@app.post("/vocabulary")
async def set_vocabulary(body: VocabularyBody) -> dict:
    text = body.text.strip()
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="vocabulary must be <= 2000 chars")
    app.state.vocabulary = text
    return {"text": text}


ALLOWED_MODELS = (
    # Local (Ollama)
    "phi3",
    "phi4-mini:3.8b",
    "mistral",
    "llama3.1",
    "qwen2.5",
    "qwen3:8b",
    # Cloud — require their respective API keys
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4-5",
)


class ModelBody(BaseModel):
    model: str


@app.get("/model")
async def get_model() -> dict:
    return {"model": app.state.ollama_model, "allowed": list(ALLOWED_MODELS)}


async def _prewarm_model(model: str) -> None:
    """Force Ollama to load the model into memory with a tiny dummy chat.

    Broadcasts ai_status so the UI shows loading -> ok / offline transitions.
    Runs in the background; failures are logged but don't crash the worker.
    """
    await app.state.hub.broadcast({"type": "ai_status", "state": "loading", "model": model})
    try:
        await app.state.llm.chat(
            messages=[{"role": "user", "content": "ping"}],
            model=model,
            format=None,
            temperature=0.0,
        )
        await app.state.hub.broadcast({"type": "ai_status", "state": "ok", "model": model})
    except Exception as exc:  # httpx.HTTPError, timeout, etc.
        print(f"[model] prewarm failed for {model}: {exc}", file=sys.stderr)
        await app.state.hub.broadcast({
            "type": "ai_status",
            "state": "offline",
            "model": model,
            "error": str(exc),
        })


@app.post("/model")
async def set_model(body: ModelBody) -> dict:
    if body.model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"model must be one of {ALLOWED_MODELS}")
    provider = provider_of(body.model)
    if provider == "openai" and not app.state.llm.openai_set:
        raise HTTPException(status_code=400, detail="OpenAI API key not set")
    if provider == "anthropic" and not app.state.llm.anthropic_set:
        raise HTTPException(status_code=400, detail="Anthropic API key not set")
    app.state.ollama_model = body.model
    app.state.extractor.set_model(body.model)
    # Kick off a background pre-warm. The UI sees `loading` immediately and
    # transitions to `ok` (or `offline`) when the model finishes loading.
    asyncio.create_task(_prewarm_model(body.model))
    return {"model": body.model}


class ApiKeyBody(BaseModel):
    provider: str  # "openai" | "anthropic"
    key: str  # empty string clears


@app.get("/api-keys")
async def get_api_keys() -> dict:
    # Never return the values themselves — only whether each is set.
    return {
        "openai": app.state.llm.openai_set,
        "anthropic": app.state.llm.anthropic_set,
    }


@app.post("/api-keys")
async def set_api_key(body: ApiKeyBody) -> dict:
    if body.provider == "openai":
        app.state.llm.set_openai_key(body.key)
        return {"openai": app.state.llm.openai_set}
    if body.provider == "anthropic":
        app.state.llm.set_anthropic_key(body.key)
        return {"anthropic": app.state.llm.anthropic_set}
    raise HTTPException(status_code=400, detail="provider must be 'openai' or 'anthropic'")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    hub: Hub = app.state.hub
    await hub.connect(ws)
    s: SessionState = app.state.session
    await ws.send_json({
        "type": "state",
        "state": s.recording_state,
        "session_id": s.session_id,
    })
    # Also send a snapshot of any existing insights, so a late client catches up.
    for ins in s.insights:
        await ws.send_json({"type": "insight", "insight": _insight_to_dict(ins)})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
