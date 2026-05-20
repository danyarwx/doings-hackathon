# PRD: Local Meeting Intelligence — Doings.ai × CF Hackathon 2026

**Version:** 2.0 (Steps 2–3 shipped; Step 4 in build)
**Team:** 3 people · 3 lanes · 4 milestones
**Status:** Steps 1–2 shipped; Step 3 (LLM extraction) backend done, UI integration in progress
**Stack:** React 18 + Vite + TypeScript + Tailwind · pywhispercpp (whisper.cpp) · FastAPI · HuggingFace Transformers (Qwen3)

---

## 0. What changed in v2.0

Steps 1 and 2 shipped. Step 3 is partially built: `model.py` runs and produces structured extractions; the React UI needs to wire up the insight panel. The LLM stack changed from the Ollama path described in v1.2.

| Topic | v1.2 | v2.0 |
|---|---|---|
| Step 2 status | 🚧 in build | ✅ shipped — FastAPI + WS + delivery + Start/Stop working |
| Step 3 status | roadmap only | 🚧 backend done (`model.py`), UI insight panel pending |
| LLM runtime | Ollama (Mistral / Phi-3) | **HuggingFace Transformers pipeline** — `Qwen3-0.6B` default (CPU), `Qwen3-8B` for GPU |
| LLM process | in-process with FastAPI | **Separate microservice** — `model.py` runs on `:8001`; backend calls it via `POST /segments` |
| Recording states | `idle \| recording \| stopping` | **+ `paused`** — capture subprocess can be suspended and resumed within the same session |
| Session history | none | **In-memory history** — past sessions stored at runtime; `/history` and `/history/{id}` endpoints |
| Insight model | loosely described | **Typed `Insight` dataclass** — id, type, text, source_quote, language, confidence, needs_review, status |
| Requirement schema | free-form text | **Jira-compatible** — `issuetype` (Story/Task/Bug/Epic), `summary`, `description`, `acceptance_criteria`, `invest_validation`, `priority`, `assignee`, `duedate`, `labels`, `story_points` |
| Extraction trigger | per-segment | **Buffered batch** — triggers every `BUFFER_TRIGGER` segments (default 4) over a rolling `CONTEXT_WINDOW` of 10 |
| WS message types | `segment`, `delivery`, `state` | **+ `insight`** — broadcast when extraction produces new items; replayed on reconnect |

---

## 1. Problem

Meeting tools are cloud-bound. Audio leaves the laptop, transcripts arrive late, and the structured
insight engineering teams need is never in the export. For Telekom, Siemens, and Volkswagen —
the target audience — this is a hard blocker: internal conversations cannot touch third-party clouds.

**What they want instead:** Local STT that the team owns. A stream they control.
Text leaves the machine only over one configurable HTTPS endpoint, on their terms. And when
structured requirements are extracted, they arrive in a format the team can act on immediately.

---

## 2. Goal

Build a local meeting assistant with four guarantees:

1. **Audio never leaves the device.** whisper.cpp runs fully on-device, offline-capable.
2. **Transcript appears as you talk.** Chunked, rolling transcription — not a post-meeting summary.
3. **Every segment is delivered.** Fanned out to both the local React UI and `staging.doings.de/stt`.
4. **Requirements are extracted live.** A local LLM classifies segments and surfaces structured, Jira-compatible items during the meeting — not after.

**Demo success:** a live meeting is transcribed in German and English, requirements appear as
approve/reject cards in the insights panel, and the final session exports Jira-ready tickets.

---

## 3. Scope

### Core MVP — the demo cannot happen without these

- Local multilingual transcription (German + English, auto-detected per segment)
- HTTPS POST to `staging.doings.de/stt` for every segment
- Offline STT — no network required for capture or transcription
- Live-updating React transcript with delivery status
- LLM extraction → approve/reject insight cards in the UI
- Session pause/resume within a single session ID

### Stretch — nice to have by the final milestone

- Speaker attribution (pyannote-audio as delayed annotation layer)
- System audio / loopback capture (Windows WASAPI)
- PyInstaller-built Windows `.exe`
- Export session as markdown or PDF (JSON export is core)
- Jira API direct POST from the UI

### Explicitly out of scope

- Cloud ASR of any kind
- Multi-user collaborative view
- Authentication or persistent storage (past sessions are in-memory, lost on restart)
- Inline transcript editing (deferred from Step 2)

---

## 4. Target audience

**Telekom · Siemens · Volkswagen** — large German engineering orgs in regulated industries.

Every architectural decision flows from this:
- Raw audio must never leave the device
- Offline operation is required (secure on-site facilities)
- German is a first-class language — not an afterthought
- The HTTPS endpoint must be swappable per environment (staging → prod) without touching the pipeline
- Extracted requirements must land in the team's existing tooling (Jira-compatible schema)

---

## 5. Architecture — four processes, one local app

Each process is isolated. The demo still works if `model.py` or diarization breaks.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              LOCAL MACHINE                               │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐  │
│  │  capture/    │────►│  whisper.cpp │────►│  backend/server.py       │  │
│  │  capture.py  │ PCM │  (pywhisper) │segs │  :8000                   │  │
│  │              │/WAV │              │     │                          │  │
│  │ sounddevice  │     │ multilingual │     │  POST /segments          │  │
│  │ 2s+200ms     │     │ timestamped  │     │  WebSocket /ws           │  │
│  │ overlap      │     │              │     │  POST /control/*         │  │
│  └──────────────┘     └──────────────┘     └───────────┬──────────────┘  │
│                                                        │                 │
│                                              ┌─────────▼─────────────┐   │
│                                              │  model.py             │   │
│                                              │  :8001                │   │
│                                              │                       │   │
│                                              │  HuggingFace          │   │
│                                              │  Qwen3-0.6B (CPU)     │   │
│                                              │  Qwen3-8B  (GPU)      │   │
│                                              │                       │   │
│                                              │  buffer 4 segs →      │   │
│                                              │  extract → Insights   │   │
│                                              └───────────────────────┘   │
│                                                        │                 │
│  ┌─────────────────────────────────────────────────┐   │ Insight JSON    │
│  │  React UI (localhost:5173)                      │◄──┘                 │
│  │  Live transcript · Delivery · Insights panel    │◄── WS :8000/ws      │
│  │  Start / Pause / Stop / Export                  │                     │
│  └─────────────────────────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTPS POST (text only)
                                 ▼
                     staging.doings.de/stt
```

---

## 6. Component specifications

### 01 — React UI
**Tech:** React 18 · Vite · TypeScript · Tailwind CSS
**Style:** Vision-UI-inspired dark/glassy aesthetic
**Runs:** `localhost:5173` in browser

Responsibilities:
- Live transcript stream — segments appear via WebSocket `{"type":"segment"}`
- Delivery status panel — per-segment confirmed ✓ / pending ⟳ / failed ✗
- **Insights panel** — approve/reject cards from `{"type":"insight"}` messages; status toggles sent back to backend
- Session controls — Start, Pause, Stop, Export JSON; map to `POST /control/*`
- Past session history — list from `GET /history`, re-load a session via `GET /history/{id}`
- On WS reconnect — backend replays all current-session insights automatically
- Speaker chips — non-blocking stretch when diarization annotates a segment

Layout (3-column desktop):
```
┌───────────────────────────────────────────────────────────────────────┐
│ ● Recording  00:14:32   Segs: 47   Delivered: 46/47   [▶][⏸][■][↓]  │
├─────────────────────────┬─────────────────────┬────────────────────────┤
│  LIVE TRANSCRIPT        │  DELIVERY STATUS    │  AI INSIGHTS           │
│  (col 6)                │  (col 3)            │  (col 3)               │
│                         │                     │                        │
│  [00:12.4] [DE]         │  seg-047  ✓         │  REQ  confidence: 0.90 │
│  Das System muss...     │  seg-046  ✓         │  Given a logged-in     │
│                         │  seg-045  ⟳         │  user, when they...    │
│  [00:17.0] [EN]         │  seg-044  ✓         │  [✓ Approve] [✗ Reject]│
│  Auth should use        │                     │                        │
│  OAuth 2.0              │                     │  ACT  confidence: 0.90 │
│                         │                     │  Set up OAuth 2.0      │
│                         │                     │  [✓ Approve] [✗ Reject]│
├─────────────────────────┴─────────────────────┴────────────────────────┤
│  [▶ Start]  [⏸ Pause]  [■ Stop]  [↓ Export]                           │
└────────────────────────────────────────────────────────────────────────┘
```

### 02 — Capture service
**Tech:** `sounddevice` (mic, all platforms) · `pywhispercpp` (whisper.cpp in-process)
**Runs:** Python subprocess spawned by `POST /control/start`; terminated by `/control/pause` or `/control/stop`

Responsibilities:
- Mic input: continuous `sounddevice.InputStream` at 16kHz mono
- Fixed 2-second chunks with 200ms overlap
- pywhispercpp model loaded once in-process (no per-chunk subprocess overhead)
- Each segment POSTed to `backend/server.py` at `http://localhost:8000/segments`
- CLI flags: `--api-url`, `--model` (default `tiny`), `--language` (optional, auto-detected if absent)
- Session ID injected via `CAPTURE_SESSION_ID` env var by the backend on spawn

Chunk parameters:
```
SAMPLE_RATE      = 16000
CHUNK_SECONDS    = 2.0
OVERLAP_SECONDS  = 0.2
CALLBACK_BLOCKSIZE = 1600  # 100ms
```

### 03 — FastAPI fan-out (backend/server.py)
**Tech:** FastAPI · httpx · WebSocket
**Runs:** `uvicorn backend.server:app --port 8000`

Responsibilities:
- `POST /segments` — accept segment from capture, broadcast WS `segment` message, dispatch delivery + model tasks concurrently
- `GET|POST /control/start` — spawn capture subprocess, mint new session ID (or resume if paused)
- `POST /control/pause` — SIGTERM capture process, keep session ID and segments; state → `paused`
- `POST /control/stop` — SIGTERM capture process, state → `idle`; archives session to in-memory history
- `GET /state` — current recording state + segment/delivery counts
- `GET /session/export` — full segment list for current session
- `GET /history` — list of archived past sessions (newest first)
- `GET /history/{session_id}` — full segment list for a past session
- `WebSocket /ws` — broadcast target; replays current state + all insights on connect
- Delivery: `POST` to `DOINGS_ENDPOINT` (default `https://staging.doings.de/stt`) with exponential backoff (3 attempts, 1s/2s/4s); broadcast `delivery` status update after each attempt
- Model forwarding: `POST MODEL_URL/segments` (default `http://localhost:8001`) per segment; on `{"status":"buffered"}` response does nothing; on full extraction result, converts to `Insight` objects and broadcasts `insight` WS messages

Recording state machine:
```
idle ──start──► recording ──pause──► paused ──start──► recording
                    │                                      │
                   stop                                  stop
                    │                                      │
                    └──────────────► idle ◄────────────────┘
```

WebSocket message types (backend → UI):
```json
{"type": "segment",  "segment": { "id", "session_id", "text", "start_s", "end_s", "lang" }}
{"type": "delivery", "id": "seg-047", "status": "pending|delivered|failed", "attempts": 1}
{"type": "state",    "state": "idle|recording|paused|stopping", "session_id": "..."}
{"type": "insight",  "insight": { "id", "segment_id", "type", "text", "source_quote",
                                  "language", "confidence", "needs_review", "status" }}
```

### 04 — LLM extraction server (model.py)
**Tech:** HuggingFace Transformers `pipeline("text-generation")` · FastAPI
**Runs:** separate process `uvicorn model:app --port 8001`
**Models:**

| Model | VRAM / RAM | Speed | Use when |
|---|---|---|---|
| `Qwen/Qwen3-0.6B` | ~2GB RAM | Fast (CPU) | Default — hackathon demo, CPU-only hardware |
| `Qwen/Qwen3-8B` | ~16GB VRAM | Strong | GPU available; better extraction quality |
| `google/gemma-3-4b-it` | ~8GB VRAM | Moderate | Alternative GPU path |

Responsibilities:
- `POST /segments` — buffer segment; trigger extraction every `BUFFER_TRIGGER` (default 4) segments
- Extraction uses a rolling context window of the last `CONTEXT_WINDOW` (default 10) segments
- Returns `{"status":"buffered"}` until trigger threshold; returns full `ExtractionResult` when fired
- `POST /sessions/{session_id}/flush` — force extraction of remaining buffer (call on session end)
- `GET /sessions/{session_id}/context` — inspect current rolling context text
- `GET /health` — model load status, device, buffer config
- `WebSocket /ws/{session_id}` — push extraction results to any connected dashboard directly

Extraction output schema (what model.py returns to backend):
```json
{
  "requirements": [
    {
      "issuetype": "Story|Task|Bug|Epic",
      "summary": "short concise title (Jira-friendly)",
      "description": {
        "user_story": {
          "given": "context of the user",
          "when": "user action or trigger",
          "then": "expected system behavior"
        },
        "acceptance_criteria": ["criterion 1", "criterion 2"],
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
      "labels": ["frontend", "backend", "auth"],
      "story_points": null
    }
  ],
  "action_items": [
    { "task": "short imperative sentence", "owner": "name or null", "deadline": null, "priority": "high|medium|low" }
  ],
  "decisions": [
    { "summary": "what was decided" }
  ],
  "topics": ["topic 1", "topic 2"]
}
```

Insight types surfaced to the UI after backend conversion:
- `requirement` — user story from Given/When/Then; confidence derived from priority (`high→0.90`, `medium→0.80`, `low→0.70`); `needs_review` = true if any INVEST criterion is false
- `action_item` — formatted as `"{task} — {owner}"` if owner present; confidence 0.90
- `decision` — summary text; confidence 0.85

### 05 — Diarization worker (stretch)
**Tech:** pyannote-audio
**Runs:** optional Python subprocess, non-blocking

Responsibilities:
- Parallel WAV processing, a few seconds behind live transcript
- Produces speaker segments with start/end times → patches existing segments in backend
- Backend broadcasts speaker labels over WS as additional segment metadata
- **Must never be a demo dependency.** Crash does not affect the session.

---

## 7. Key technical decisions

**Two FastAPI processes, not one.** `backend/server.py` (:8000) owns the session lifecycle, WS hub,
delivery, and capture subprocess. `model.py` (:8001) owns the LLM and buffering. Separating them
means the LLM can block on inference without stalling the transcript stream. The backend forwards
segments and handles the response asynchronously.

**Buffered extraction.** Running the LLM on every single segment is too slow and too noisy.
`BUFFER_TRIGGER=4` gives the LLM enough context for meaningful extraction while keeping latency
under ~10 seconds on CPU. `CONTEXT_WINDOW=10` ensures the LLM always sees the broader conversation,
not just the trigger batch.

**Qwen3, not Ollama.** HuggingFace Transformers lets us load the model once in-process, skip the
Ollama HTTP layer, and run on CPU with `Qwen3-0.6B` without requiring a separate server install.
`/no_think` in the system prompt disables Qwen3's chain-of-thought for faster, deterministic JSON.

**Jira-compatible schema.** INVEST validation and `issuetype`/`story_points`/`labels` fields mean
the Step 4 ingest can target Jira's REST API directly — or any compatible tracker — without a
translation layer.

**Pause preserves session.** `/control/pause` terminates the capture subprocess but keeps the
session ID and all accumulated segments. `/control/start` while paused resumes into the same
session. Only `/control/stop` archives and resets.

**Insight replay on reconnect.** When a new WS client connects, the backend replays all
`Insight` objects stored in `SessionState.insights`. This means a browser refresh never loses
already-extracted items.

**Mic is the guaranteed path.** System audio capture is OS-specific and fragile. The demo is
built around mic input. Loopback is a bonus added only after the mic path is solid.

**One configurable endpoint.** `DOINGS_ENDPOINT` env var controls where segments are delivered.
`MODEL_URL` controls where the LLM server lives. Staging → prod swap requires no code change.

---

## 8. Team lanes

Three people, three lanes — blockers in one lane don't cascade to others.

### Person 01 — React UI
- Wire `{"type":"insight"}` WS messages into the insights panel
- Approve / reject card interaction (POST status update back to backend or local state)
- Confidence indicator and `needs_review` flag display per card
- Pause button (maps to `POST /control/pause`; resumes with `POST /control/start`)
- Past session history drawer using `GET /history` + `GET /history/{id}`
- Export JSON button for both current and past sessions

### Person 02 — Capture + STT
- `--model tiny` default (fast); `--model small` or `--model medium` fallback for German accuracy
- `--language` passthrough from `POST /control/start` body `{"language": "de"}`
- Stable `seg-NNN` IDs + `CAPTURE_SESSION_ID` env var handling (already wired in backend)
- Loopback audio via PyAudioWPatch (Windows WASAPI) — stretch after mic path is demo-ready

### Person 03 — Backend + Delivery
- `POST /sessions/{session_id}/flush` call on `/control/stop` to drain remaining model buffer
- Insight status update endpoint (for UI approve/reject if stored server-side)
- Diarization merge into transcript segments (stretch)
- `model.py` reliability: health-check before forwarding; graceful fallback if `:8001` is down

---

## 9. Product Roadmap

Each step is a fully working, demoable product on its own. Do not start a step until the previous
one works end-to-end.

```
STEP 1          STEP 2          STEP 3          STEP 4
────────        ────────        ────────        ────────
Terminal        Beautiful       Local LLM       Requirements
live STT    ──► Web UI      ──► Analysis    ──► & Tickets
✅ shipped      ✅ shipped      🚧 in build     ○ next
```

---

### Step 1 — Terminal Live STT ✦ ✅ Shipped
*"Speak into the mic. See text in the terminal. Nothing else."*

**Done:** mic → pywhispercpp → stdout with `[mm:ss.s → mm:ss.s] [DE/EN] text` format.
German + English auto-detected, fully offline, 2s+200ms-overlap chunks at 16kHz.

---

### Step 2 — Beautiful Web UI ✅ Shipped
*"The same live transcript, now in a polished React interface."*

**Done:**
- FastAPI bridge receiving segments, broadcasting over `/ws`, retrying HTTPS delivery
- React dashboard with live transcript, delivery status panel, Start/Stop controls
- `/control/pause` and `/control/stop` with correct state machine
- In-memory session history with `/history` and `/history/{id}`
- Export session as JSON via `GET /session/export`

---

### Step 3 — Local LLM Analysis 🚧 In Build
*"The transcript is now understood, not just captured."*

**Backend done:** `model.py` buffers segments, runs Qwen3 extraction, returns structured JSON.
`backend/server.py` converts extraction results to `Insight` objects and broadcasts them over WS.

**Remaining:**
- [ ] React insights panel — renders approve/reject cards from `{"type":"insight"}` WS messages
- [ ] Confidence indicator and `needs_review` highlight per card
- [ ] Approve / reject interaction (client-side state toggle minimum; server-side persist as stretch)
- [ ] Pause → `POST /sessions/{session_id}/flush` on stop to drain remaining buffer
- [ ] Model health indicator in the UI status bar (is `:8001` reachable?)
- [ ] `BUFFER_TRIGGER` and `CONTEXT_WINDOW` documented in `.env.example`

**Done when:** Speaking a requirement in German or English produces a structured card in the UI
within ~15 seconds on CPU (`Qwen3-0.6B`), which the user can approve or reject with one click.

---

### Step 4 — Requirements & Tickets ○ Next
*"Approved items become engineering artifacts."*

Aggregate the session's approved insights into a structured requirements document and POST it to
Doings.ai's pipeline (or a Jira-compatible endpoint). This is the full-circle moment: spoken
meeting → structured spec → engineering backlog.

**What it does:**
- Collect all approved `Insight` objects from the session
- Final LLM enrichment pass: assign requirement IDs, link related items, normalize language
- Generate Jira-compatible ticket payloads (title, description, acceptance criteria, story points)
- POST to `staging.doings.de/stt` (or a separate Doings ingest endpoint / Jira API)
- "Requirements" view in the React UI — clean, exportable list; the session's final deliverable

**Deliverables:**
- [ ] Session summary collector — aggregates approved insights at session end
- [ ] Final enrichment prompt (IDs, priority, linked items, normalized text)
- [ ] Requirements document schema (see below)
- [ ] Ticket payload generation per approved requirement
- [ ] POST to ingest endpoint with retry (`DOINGS_INGEST_URL` env var)
- [ ] "Requirements" view in React UI — numbered list, exportable as JSON
- [ ] Export as markdown (stretch)
- [ ] Pre-recorded DE/EN fallback demo clip covering all four steps
- [ ] Full live demo rehearsed at least twice

**Requirements document schema (Step 4 output):**
```json
{
  "session": {
    "id": "sess-20260520-001",
    "started_at": "2026-05-20T09:00:00Z",
    "duration_seconds": 1421,
    "language": "de+en"
  },
  "requirements": [
    {
      "id": "REQ-001",
      "issuetype": "Story",
      "summary": "Concurrent user capacity",
      "user_story": {
        "given": "a registered user on the platform",
        "when": "they perform any core action simultaneously with 500 others",
        "then": "the system must respond within 2 seconds without degradation"
      },
      "acceptance_criteria": [
        "Load test passes at 500 concurrent users",
        "Response time stays under 2s at peak load"
      ],
      "priority": "high",
      "labels": ["backend", "performance"],
      "story_points": 8,
      "language": "de",
      "source_quote": "Das System muss mindestens 500 Nutzer unterstützen.",
      "timestamp_start_s": 12.4,
      "timestamp_end_s": 15.1,
      "human_verified": true,
      "linked_items": []
    }
  ],
  "action_items": [
    {
      "id": "ACT-001",
      "task": "Set up load testing environment",
      "owner": null,
      "deadline": null,
      "human_verified": true
    }
  ],
  "decisions": [
    {
      "id": "DEC-001",
      "summary": "OAuth 2.0 selected as the authentication standard",
      "human_verified": true
    }
  ]
}
```

**Tech:** FastAPI enrichment endpoint · React requirements view · Doings / Jira ingest API

---

### Roadmap summary

| Step | Name | Output | Demoable alone |
|---|---|---|---|
| 1 | Terminal Live STT | Text in terminal | ✅ Yes |
| 2 | Beautiful Web UI | Live transcript in browser + delivery | ✅ Yes |
| 3 | Local LLM Analysis | Approve/reject extracted items live | ✅ Yes (once UI panel is wired) |
| 4 | Requirements & Tickets | Structured spec + tickets → Doings / Jira | ✅ Yes |

**Hard rule:** each step must work end-to-end before the next begins.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `Qwen3-0.6B` extraction quality poor on small context | Increase `BUFFER_TRIGGER` to 6–8 for more context; switch to `Qwen3-8B` if GPU available |
| Model inference blocks transcript pipeline | `model.py` is a separate process; backend forwards asynchronously — transcript is never blocked |
| `staging.doings.de/stt` endpoint unavailable | Mock locally with `backend/echo_endpoint.py`; set `DOINGS_ENDPOINT=http://localhost:8001/stt` |
| German STT accuracy poor on `tiny` model | Switch `--model small` or `--model medium` in `/control/start` body; test on DE audio before demo |
| UI loses insights on browser refresh | Backend replays all `session.insights` on new WS connect — no data loss |
| Pause/resume session ID mismatch | Capture spawned with same `CAPTURE_SESSION_ID` env var on resume — IDs are stable |
| `model.py` crashes mid-session | Backend logs warning and skips insights; transcript + delivery continue unaffected |
| Diarization blocks demo | Separate optional process — demo works without it by design |
| Live demo audio fails | Pre-recorded DE/EN fallback clip, tested end-to-end before showtime |
| LLM JSON parse failure | `clean_json()` strips fences and Qwen3 `<think>` tags; `parse_error` field returned instead of crash |

---

## 11. Local dev setup (quick start)

```bash
# 1. Python environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install fastapi uvicorn httpx sounddevice numpy pywhispercpp \
            transformers accelerate torch

# 2. Download a Whisper model (tiny for dev; small/medium for German accuracy)
python -c "from pywhispercpp.model import Model; Model('tiny')"

# 3. Run all four processes in separate terminals

# Terminal 1 — FastAPI fan-out backend
uvicorn backend.server:app --port 8000 --reload

# Terminal 2 — LLM extraction server
uvicorn model:app --port 8001 --reload
# Override model: MODEL=Qwen/Qwen3-8B uvicorn model:app --port 8001

# Terminal 3 — React UI
cd ui && npm install && npm run dev   # → http://localhost:5173

# Terminal 4 — Optional: local echo endpoint to mock staging.doings.de
uvicorn backend.echo_endpoint:app --port 8002
# Then: DOINGS_ENDPOINT=http://localhost:8002/stt uvicorn backend.server:app --port 8000

# 4. Start recording from the UI or directly:
curl -X POST http://localhost:8000/control/start \
     -H "Content-Type: application/json" \
     -d '{"language": "de"}'
```

Environment variables:
```
DOINGS_ENDPOINT   # default: https://staging.doings.de/stt
MODEL_URL         # default: http://localhost:8001  (empty string disables model forwarding)
CAPTURE_CMD       # override full capture command (shlex-split)
MODEL             # HuggingFace model ID for model.py (default: Qwen/Qwen3-0.6B)
BUFFER_TRIGGER    # segments per extraction batch (default: 4)
CONTEXT_WINDOW    # rolling context size in segments (default: 10)
```

---

## 12. Open questions

- Does Doings.ai have a separate ingest endpoint for Step 4 requirements, or does the same
  `staging.doings.de/stt` receive both raw segments and final requirement documents?
- Should approve/reject status be persisted server-side (backend stores it in `SessionState`)
  or is client-side-only state acceptable for the hackathon demo?
- Is there a preferred Jira project / API endpoint for the Step 4 ticket POST, or will Doings
  handle the Jira integration on their side?
- Demo hardware confirmed CPU-only? (`Qwen3-0.6B` is the safe default; switch to `Qwen3-8B` if GPU available)
- Should the UI language (labels, placeholders) be German, English, or switchable?
- Any domain vocabulary (acronyms, product names) to add as Whisper initial prompt hints for better German STT?
