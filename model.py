"""
extraction_server.py
====================
FastAPI server that receives transcript segments from the whisper.cpp
pipeline (via POST /segments) and runs local LLM extraction using either:

  • Qwen/Qwen3-8B            (recommended, 100+ languages, ~16GB VRAM)
  • google/gemma-3-4b-it     (lighter, ~8GB VRAM)

Extracted JSON (action items, requirements, decisions) is stored per
session and broadcast via WebSocket to any connected dashboard clients.

Install
-------
    pip install fastapi uvicorn httpx transformers accelerate torch websockets

Run
---
    # with Qwen3-8B (default)
    uvicorn extraction_server:app --host 0.0.0.0 --port 8000 --reload

    # with Gemma 3 4B
    MODEL=google/gemma-3-4b-it uvicorn extraction_server:app --port 8000

Then point the whisper.cpp pipeline at it:
    python main.py --api-url http://localhost:8000 --model base
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import torch
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from transformers import pipeline

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_ID: str = os.getenv(
    "MODEL",
    "Qwen/Qwen3-0.6B",        # CPU-friendly; set MODEL=Qwen/Qwen3-8B for GPU
)

# How many segments to buffer before triggering extraction.
# Lower = more real-time, higher = more context for the LLM.
BUFFER_TRIGGER: int = int(os.getenv("BUFFER_TRIGGER", "4"))

# Keep the last N segments as sliding context (avoids re-processing old text)
CONTEXT_WINDOW: int = int(os.getenv("CONTEXT_WINDOW", "10"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("extraction_server")

# ---------------------------------------------------------------------------
# System prompt  — shared by both models
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a requirements extraction agent for meeting transcripts.

Given a transcript chunk, return ONLY a valid JSON object with:
- NO preamble
- NO markdown fences
- NO explanation
- Output nothing except the JSON

Schema:
{
  "requirements": [
    {
      "issuetype": "Story|Task|Bug|Epic",
      "summary": "short concise title",
      "description": {
        "user_story": {
          "given": "context of the user",
          "when": "user action or trigger",
          "then": "expected system behavior"
        },
        "acceptance_criteria": [
          "criterion 1",
          "criterion 2"
        ],
        "invest_validation": {
          "independent": true,
          "negotiable": true,
          "valuable": true,
          "estimable": true,
          "small": true,
          "testable": true
        }
      },
      "priority": "high|medium|low",
      "assignee": "name or null",
      "duedate": "date string or null",
      "labels": ["frontend", "backend", "auth", "ui"],
      "story_points": number or null
    }
  ],
  "action_items": [
    {
      "task": "short imperative sentence",
      "owner": "name or null",
      "deadline": "date string or null",
      "priority": "high|medium|low"
    }
  ],
  "decisions": [
    {
      "summary": "what was decided"
    }
  ],
  "topics": [
    "topic 1",
    "topic 2"
  ]
}

Requirement Formatting Rules:
- Every requirement MUST be written as a user story using:
  Given [context of the user],
  When [the user action],
  Then [what the system must do].

- Acceptance criteria MUST:
  - Be in list format
  - Be specific and testable
  - Describe observable system behavior
  - Avoid vague wording such as "works well" or "user friendly"

INVEST Rules:
- Independent:
  The requirement should be implementable without depending on another story.

- Negotiable:
  The story should describe intent, not rigid implementation details.

- Valuable:
  The requirement must provide clear user or business value.

- Estimable:
  The story must contain enough clarity for estimation.

- Small:
  The scope should fit within a single sprint or iteration.

- Testable:
  Acceptance criteria must allow verification of completion.

Extraction Rules:
- Include ONLY requirements explicitly mentioned or strongly implied.
- Split large combined requirements into smaller independent stories when possible.
- Do NOT invent technical details not present in the transcript.
- If no relevant information exists, return empty arrays.
- Keep summaries concise and Jira-friendly.
- Labels should reflect domains or components discussed.
- Story points should be estimated only if complexity is reasonably inferable.

For Qwen3:
/no_think
"""

# ---------------------------------------------------------------------------
# HuggingFace model loader  (runs once at startup)
# ---------------------------------------------------------------------------

_pipe: Any = None          # transformers pipeline, set during lifespan
_pipe_lock = threading.Lock()


def load_model(model_id: str) -> Any:
    """Load model + tokenizer into a text-generation pipeline."""
    log.info("Loading model %s …", model_id)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if device == "cuda" else torch.float32

    gen_pipeline = pipeline(
        "text-generation",
        model=model_id,
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        device=None if device == "cuda" else device,
        trust_remote_code=True,
    )
    log.info("Model loaded on %s", device)
    return gen_pipeline


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

def clean_json(raw: str) -> str:
    """Strip markdown fences and whitespace from LLM output."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```$", "", raw)
    # Qwen3 thinking tags
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    return raw.strip()


def build_prompt(transcript: str, model_id: str) -> list[dict]:
    """Build chat messages list for the given model."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Transcript:\n{transcript}"},
    ]


def extract(transcript: str) -> dict:
    """Run the local LLM and parse structured JSON from transcript text."""
    global _pipe
    if _pipe is None:
        return {"error": "model not loaded"}

    messages = build_prompt(transcript, MODEL_ID)

    with _pipe_lock:
        outputs = _pipe(
            messages,
            max_new_tokens=800,
            do_sample=False,      # greedy — most deterministic JSON
            temperature=None,     # must be None when do_sample=False
            top_p=None,
        )

    # Different models surface the response differently
    raw_output = outputs[0]
    if isinstance(raw_output, dict):
        # pipeline returns list of dicts with "generated_text"
        generated = raw_output.get("generated_text", "")
        if isinstance(generated, list):
            # chat format: last message is assistant reply
            generated = generated[-1].get("content", "")
    else:
        generated = str(raw_output)

    cleaned = clean_json(generated)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("JSON parse failed: %s\nRaw output: %s", exc, cleaned[:300])
        return {"raw": cleaned, "parse_error": str(exc)}


# ---------------------------------------------------------------------------
# Session buffer  — accumulates segments per session_id
# ---------------------------------------------------------------------------

class SessionBuffer:
    """Thread-safe per-session transcript buffer with rolling context."""

    def __init__(self):
        self._segments: dict[str, deque] = defaultdict(lambda: deque(maxlen=CONTEXT_WINDOW))
        self._pending:  dict[str, list]  = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, session_id: str, segment: dict) -> list[dict] | None:
        """
        Add a segment.  Returns the pending batch for extraction when the
        trigger threshold is reached, else None.
        """
        with self._lock:
            self._segments[session_id].append(segment)
            self._pending[session_id].append(segment)
            if len(self._pending[session_id]) >= BUFFER_TRIGGER:
                batch = list(self._pending[session_id])
                self._pending[session_id].clear()
                return batch
        return None

    def flush(self, session_id: str) -> list[dict]:
        """Drain any remaining pending segments (called on session end)."""
        with self._lock:
            batch = list(self._pending.get(session_id, []))
            self._pending.pop(session_id, None)
            return batch

    def context(self, session_id: str) -> str:
        """Return rolling transcript text for context (last N segments)."""
        with self._lock:
            segs = list(self._segments.get(session_id, []))
        return " ".join(s["text"] for s in segs).strip()


buffer = SessionBuffer()

# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

_ws_clients: dict[str, list[WebSocket]] = defaultdict(list)
_ws_lock = threading.Lock()


async def broadcast(session_id: str, payload: dict) -> None:
    """Send JSON payload to all dashboard clients watching this session."""
    with _ws_lock:
        clients = list(_ws_clients.get(session_id, []))
    dead = []
    for ws in clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    if dead:
        with _ws_lock:
            for d in dead:
                try:
                    _ws_clients[session_id].remove(d)
                except ValueError:
                    pass

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model before serving requests, unload on shutdown."""
    global _pipe
    _pipe = load_model(MODEL_ID)
    yield
    log.info("Shutting down.")


app = FastAPI(
    title="Real-time Transcript Extraction",
    description="Receives whisper.cpp segments → local LLM → structured JSON",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Segment(BaseModel):
    id:         str
    session_id: str
    text:       str
    start_s:    float
    end_s:      float
    lang:       str | None = None


class ExtractionResult(BaseModel):
    session_id:   str
    segment_ids:  list[str]
    extracted_at: str
    model:        str
    data:         dict

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/segments", response_model=ExtractionResult | dict)
async def receive_segment(seg: Segment):
    """
    Called by the whisper.cpp pipeline for every transcript segment.
    Buffers segments and triggers extraction every BUFFER_TRIGGER segments.
    """
    log.debug("Received segment %s: %r", seg.id, seg.text[:60])

    batch = buffer.add(seg.session_id, seg.dict())

    if batch is None:
        # Not enough segments yet — just acknowledge
        return {"status": "buffered", "segment_id": seg.id}

    # Run extraction on the full rolling context for best results
    context_text = buffer.context(seg.session_id)
    log.info("Extracting from %d chars of context (session=%s)", len(context_text), seg.session_id)

    extracted = extract(context_text)

    result = ExtractionResult(
        session_id=seg.session_id,
        segment_ids=[s["id"] for s in batch],
        extracted_at=datetime.utcnow().isoformat() + "Z",
        model=MODEL_ID,
        data=extracted,
    )

    # Push to any connected WebSocket dashboards
    await broadcast(seg.session_id, result.dict())

    return result


@app.post("/sessions/{session_id}/flush")
async def flush_session(session_id: str):
    """
    Force extraction of any remaining buffered segments.
    Call this when the meeting ends (Ctrl-C in the whisper pipeline).
    """
    remaining = buffer.flush(session_id)
    if not remaining:
        return {"status": "nothing to flush"}

    context_text = buffer.context(session_id)
    extracted = extract(context_text)

    result = ExtractionResult(
        session_id=session_id,
        segment_ids=[s["id"] for s in remaining],
        extracted_at=datetime.utcnow().isoformat() + "Z",
        model=MODEL_ID,
        data=extracted,
    )

    await broadcast(session_id, result.dict())
    return result


@app.get("/sessions/{session_id}/context")
async def get_context(session_id: str):
    """Return the current rolling transcript context for a session."""
    return {"session_id": session_id, "context": buffer.context(session_id)}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_ID,
        "model_loaded": _pipe is not None,
        "buffer_trigger": BUFFER_TRIGGER,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint — real-time dashboard connection
# ---------------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    """
    Dashboard clients connect here to receive live extraction results.
    Connect from JS:
        const ws = new WebSocket("ws://localhost:8000/ws/<session_id>");
        ws.onmessage = e => console.log(JSON.parse(e.data));
    """
    await ws.accept()
    with _ws_lock:
        _ws_clients[session_id].append(ws)
    log.info("WebSocket client connected for session %s", session_id)
    try:
        while True:
            # Keep connection alive; server pushes, client just listens
            await ws.receive_text()
    except WebSocketDisconnect:
        with _ws_lock:
            try:
                _ws_clients[session_id].remove(ws)
            except ValueError:
                pass
        log.info("WebSocket client disconnected for session %s", session_id)


# ---------------------------------------------------------------------------
# Quick demo HTML dashboard  (open http://localhost:8000/ in browser)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Live Extraction Dashboard</title>
<style>
  body { font-family: monospace; background: #0d0d0d; color: #e0e0e0; padding: 1.5rem; }
  h1 { color: #c8e600; font-size: 1.1rem; margin-bottom: 1rem; }
  #status { font-size: 0.75rem; color: #888; margin-bottom: 1rem; }
  .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px;
          padding: 0.75rem 1rem; margin-bottom: 0.75rem; }
  .card h3 { font-size: 0.7rem; color: #666; text-transform: uppercase;
             letter-spacing: .08em; margin-bottom: 0.5rem; }
  .item { font-size: 0.8rem; padding: 3px 0; border-bottom: 1px solid #222; }
  .item:last-child { border-bottom: none; }
  .priority-high   { color: #E24B4A; }
  .priority-medium { color: #c8e600; }
  .priority-low    { color: #888; }
  input { background: #111; border: 1px solid #333; color: #ccc;
          padding: 4px 8px; font-family: monospace; font-size: 0.85rem;
          border-radius: 4px; width: 260px; }
  button { background: #c8e600; color: #000; border: none; padding: 5px 14px;
           font-family: monospace; font-size: 0.85rem; border-radius: 4px;
           cursor: pointer; margin-left: 6px; }
</style>
</head>
<body>
<h1>⚡ Live Extraction Dashboard</h1>
<div id="status">Not connected</div>
<div>
  <input id="session" placeholder="session_id  e.g. sess-20260519-120000" />
  <button onclick="connect()">Connect</button>
</div>
<div id="output" style="margin-top:1.2rem"></div>
<script>
let ws;
function connect() {
  const sid = document.getElementById('session').value.trim();
  if (!sid) return;
  if (ws) ws.close();
  ws = new WebSocket(`ws://localhost:8000/ws/${sid}`);
  document.getElementById('status').textContent = `Connecting to session: ${sid}`;
  ws.onopen  = () => document.getElementById('status').textContent = `✅ Connected — ${sid}`;
  ws.onclose = () => document.getElementById('status').textContent = `❌ Disconnected`;
  ws.onmessage = e => render(JSON.parse(e.data));
}
function render(result) {
  const d = result.data;
  let html = `<div class="card"><h3>🕐 ${result.extracted_at.slice(11,19)} — segments ${result.segment_ids.join(', ')}</h3>`;
  if (d.action_items?.length) {
    html += '<h3>✅ Action Items</h3>';
    d.action_items.forEach(i => {
      html += `<div class="item priority-${i.priority||'medium'}">
        <b>${i.task}</b> ${i.owner?'— '+i.owner:''} ${i.deadline?'by '+i.deadline:''}
      </div>`;
    });
  }
  if (d.requirements?.length) {
    html += '<h3>📋 Requirements</h3>';
    d.requirements.forEach(i => {
      html += `<div class="item priority-${i.priority||'medium'}">${i.spec}
        ${(i.labels||[]).map(l=>`<span style="color:#666">[${l}]</span>`).join(' ')}
      </div>`;
    });
  }
  if (d.decisions?.length) {
    html += '<h3>🔷 Decisions</h3>';
    d.decisions.forEach(i => `<div class="item">${i.summary}</div>`);
  }
  html += '</div>';
  document.getElementById('output').innerHTML = html + document.getElementById('output').innerHTML;
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("extraction_server:app", host="0.0.0.0", port=8000, reload=False)