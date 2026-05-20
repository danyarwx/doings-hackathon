"""FastAPI fan-out: receives segments, broadcasts to UI, posts to staging."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import shlex
import subprocess
import threading
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.delivery import deliver
from backend.state import Segment, SessionState
from capture.aggregator import ParagraphAggregator

log = logging.getLogger("backend.server")

PARAGRAPH_GAP_S = float(os.getenv("PARAGRAPH_GAP_S", "1.5"))
MAX_PARAGRAPH_S = float(os.getenv("MAX_PARAGRAPH_S", "30.0"))

# ---------------------------------------------------------------------------
# Extraction — lazy background model load
# ---------------------------------------------------------------------------

EXTRACT_TRIGGER: int = int(os.getenv("EXTRACT_TRIGGER", "4"))

_ext_pipe: Any = None
_ext_pipe_lock = threading.Lock()
_ext_ready = False


def _load_model_bg() -> None:
    global _ext_pipe, _ext_ready
    try:
        from model import MODEL_ID, load_model  # type: ignore[import]
        log.info("Loading extraction model %s …", MODEL_ID)
        pipe = load_model(MODEL_ID)
        with _ext_pipe_lock:
            _ext_pipe = pipe
            _ext_ready = True
        log.info("Extraction model ready.")
    except Exception as exc:
        log.warning("Extraction model failed to load (insights disabled): %s", exc)


class _ExtractionBuffer:
    def __init__(self) -> None:
        self._pending: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, session_id: str, seg: dict) -> list | None:
        with self._lock:
            self._pending[session_id].append(seg)
            if len(self._pending[session_id]) >= EXTRACT_TRIGGER:
                batch = list(self._pending[session_id])
                self._pending[session_id].clear()
                return batch
        return None

    def flush(self, session_id: str) -> list:
        with self._lock:
            return list(self._pending.pop(session_id, []))


_ext_buffer = _ExtractionBuffer()


def _extract_sync(text: str) -> dict:
    from model import MODEL_ID, build_prompt, clean_json  # type: ignore[import]
    with _ext_pipe_lock:
        if _ext_pipe is None:
            return {}
        outputs = _ext_pipe(
            build_prompt(text, MODEL_ID),
            max_new_tokens=800,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    raw = outputs[0]
    if isinstance(raw, dict):
        generated = raw.get("generated_text", "")
        if isinstance(generated, list):
            generated = generated[-1].get("content", "")
    else:
        generated = str(raw)
    cleaned = clean_json(generated)
    try:
        return _json.loads(cleaned)
    except Exception:
        return {}


def _map_to_insights(data: dict, batch: list, session_id: str) -> list[dict]:
    lang = (batch[-1].get("lang") or "en") if batch else "en"
    source_quote = " ".join(s["text"] for s in batch)[:200]
    results: list[dict] = []

    for item in data.get("requirements", []):
        text = item if isinstance(item, str) else item.get("summary", "")
        if not text:
            continue
        results.append({
            "id": f"ins-{uuid.uuid4().hex[:8]}",
            "session_id": session_id,
            "type": "requirement",
            "text": text,
            "source_quote": source_quote,
            "language": lang,
            "confidence": 0.80,
            "needs_review": True,
            "status": "pending",
        })

    for item in data.get("action_items", []):
        if isinstance(item, str):
            text = item
        else:
            parts = [item.get("task", "")]
            if item.get("owner"):
                parts.append(f"→ {item['owner']}")
            if item.get("deadline"):
                parts.append(f"(by {item['deadline']})")
            text = " ".join(parts)
        if not text:
            continue
        results.append({
            "id": f"ins-{uuid.uuid4().hex[:8]}",
            "session_id": session_id,
            "type": "action_item",
            "text": text,
            "source_quote": source_quote,
            "language": lang,
            "confidence": 0.85,
            "needs_review": True,
            "status": "pending",
        })

    for item in data.get("decisions", []):
        text = item if isinstance(item, str) else item.get("summary", "")
        if not text:
            continue
        results.append({
            "id": f"ins-{uuid.uuid4().hex[:8]}",
            "session_id": session_id,
            "type": "decision",
            "text": text,
            "source_quote": source_quote,
            "language": lang,
            "confidence": 0.90,
            "needs_review": False,
            "status": "pending",
        })

    return results


async def _run_extraction(session_id: str, batch: list, hub: "Hub", insight_log: list[dict]) -> None:
    if not _ext_ready:
        return
    text = " ".join(s["text"] for s in batch)
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, _extract_sync, text)
    except Exception as exc:
        log.warning("Extraction failed: %s", exc)
        return
    if not data:
        return
    for ins in _map_to_insights(data, batch, session_id):
        insight_log.append(ins)
        await hub.broadcast({"type": "insight", "insight": ins})

DEFAULT_ENDPOINT = "https://staging.doings.de/stt"

REPO_ROOT = Path(__file__).resolve().parent.parent
_win = (REPO_ROOT / ".venv" / "Scripts" / "python.exe")
CAPTURE_PYTHON = _win if _win.exists() else (REPO_ROOT / ".venv" / "bin" / "python")


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
    app.state.past_sessions = []
    app.state.insight_log: list[dict] = []
    app.state.aggregator = ParagraphAggregator(PARAGRAPH_GAP_S, MAX_PARAGRAPH_S)
    app.state.draft_ids: list[str] = []
    # Start model load in background — server is ready immediately.
    threading.Thread(target=_load_model_bg, daemon=True).start()
    yield
    proc = app.state.capture_proc
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, proc.wait),
                timeout=3.0,
            )
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


def _capture_command(language: str | None = None) -> list[str]:
    cmd_str = os.getenv("CAPTURE_CMD")
    if cmd_str:
        parts = shlex.split(cmd_str, posix=(os.name != "nt"))
    else:
        parts = [
            str(CAPTURE_PYTHON),
            "-m", "capture.main",
            "--api-url", "http://localhost:8000",
            "--model", "tiny",
        ]
    if language and "--language" not in parts:
        parts += ["--language", language]
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
    app.state.past_sessions.insert(0, snapshot)


def _utc_iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _flush_paragraph(session_id: str) -> None:
    """Emit any buffered in-progress paragraph as a final segment."""
    for merged in app.state.aggregator.flush():
        if not app.state.draft_ids:
            continue
        replaces = list(app.state.draft_ids)
        app.state.draft_ids = []
        final = Segment(
            id=f"para-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            text=merged.text,
            start_s=merged.start_s,
            end_s=merged.end_s,
            lang=merged.lang,
        )
        app.state.session.add_segment(final)
        await app.state.hub.broadcast({
            "type": "segment",
            "segment": {**_segment_to_dict(final), "is_draft": False, "replaces": replaces},
        })


async def _monitor_capture(app: FastAPI) -> None:
    proc = app.state.capture_proc
    if proc is None:
        return
    await asyncio.get_event_loop().run_in_executor(None, proc.wait)
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
        or (app.state.capture_proc is not None and app.state.capture_proc.poll() is None)
    ):
        raise HTTPException(status_code=409, detail="already recording")

    language = body.language if body else None
    resuming_from_paused = app.state.session.recording_state == "paused"
    if not resuming_from_paused:
        _archive_current_session(app)
        app.state.session.reset(session_id=_new_session_id())
        app.state.insight_log = []
        app.state.aggregator = ParagraphAggregator(PARAGRAPH_GAP_S, MAX_PARAGRAPH_S)
        app.state.draft_ids = []

    session_id = app.state.session.session_id or _new_session_id()
    if app.state.session.session_id is None:
        app.state.session.session_id = session_id

    cmd = _capture_command(language=language)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=None,
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
    if proc is None or proc.poll() is not None or app.state.session.recording_state != "recording":
        raise HTTPException(status_code=409, detail="not recording")
    app.state.session.recording_state = "paused"
    proc.terminate()
    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, proc.wait),
            timeout=3.0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await asyncio.get_event_loop().run_in_executor(None, proc.wait)
    app.state.capture_proc = None
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
    if state == "idle":
        raise HTTPException(status_code=409, detail="not recording")
    app.state.session.recording_state = "stopping"
    await app.state.hub.broadcast({
        "type": "state",
        "state": "stopping",
        "session_id": app.state.session.session_id,
    })
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, proc.wait),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await asyncio.get_event_loop().run_in_executor(None, proc.wait)
    app.state.capture_proc = None
    # Flush any buffered drafts into a final paragraph before archiving.
    if app.state.session.session_id:
        await _flush_paragraph(app.state.session.session_id)
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
    # 1. Broadcast immediately as a draft (not stored yet).
    await app.state.hub.broadcast({
        "type": "segment",
        "segment": {**_segment_to_dict(seg), "is_draft": True, "replaces": []},
    })

    # 2. Deliver raw segment to staging endpoint (unchanged behaviour).
    asyncio.create_task(_deliver_and_report(seg))

    # 3. Feed aggregator; emit final paragraph if a boundary fires.
    ready = app.state.aggregator.add(seg)
    if not ready:
        app.state.draft_ids.append(seg.id)
    else:
        for merged in ready:
            replaces = list(app.state.draft_ids)
            app.state.draft_ids = [seg.id]  # triggering seg starts next paragraph
            final = Segment(
                id=f"para-{uuid.uuid4().hex[:8]}",
                session_id=seg.session_id,
                text=merged.text,
                start_s=merged.start_s,
                end_s=merged.end_s,
                lang=merged.lang,
            )
            app.state.session.add_segment(final)
            await app.state.hub.broadcast({
                "type": "segment",
                "segment": {**_segment_to_dict(final), "is_draft": False, "replaces": replaces},
            })

    # 4. LLM extraction buffer (unchanged).
    batch = _ext_buffer.add(seg.session_id, _segment_to_dict(seg))
    if batch is not None:
        asyncio.create_task(_run_extraction(seg.session_id, batch, app.state.hub, app.state.insight_log))
    return {"accepted": True}


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
    for ins in app.state.insight_log:
        await ws.send_json({"type": "insight", "insight": ins})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
