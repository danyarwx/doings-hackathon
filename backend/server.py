"""FastAPI fan-out: receives segments, broadcasts to UI, posts to staging."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.delivery import deliver
from backend.state import Segment, SessionState

DEFAULT_ENDPOINT = "https://staging.doings.de/stt"

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
    yield
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


def _capture_command() -> list[str]:
    cmd_str = os.getenv("CAPTURE_CMD", DEFAULT_CAPTURE_CMD)
    return shlex.split(cmd_str)


def _capture_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


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


@app.post("/control/start")
async def control_start() -> dict:
    if (
        app.state.session.recording_state == "recording"
        or (app.state.capture_proc is not None and app.state.capture_proc.returncode is None)
    ):
        raise HTTPException(status_code=409, detail="already recording")
    cmd = _capture_command()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=str(REPO_ROOT),
        env=_capture_env(),
    )
    app.state.capture_proc = proc
    app.state.session.recording_state = "recording"
    asyncio.create_task(_monitor_capture(app))
    await app.state.hub.broadcast({
        "type": "state",
        "state": "recording",
        "session_id": app.state.session.session_id,
    })
    return {"pid": proc.pid}


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
    await app.state.hub.broadcast({"type": "segment", "segment": _segment_to_dict(seg)})
    asyncio.create_task(_deliver_and_report(seg))
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
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
