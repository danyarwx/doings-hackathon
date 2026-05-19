# PRD: Local Meeting Intelligence — Doings.ai × CF Hackathon 2026

**Version:** 1.2 (frontend retargeted; roadmap intact)
**Team:** 3 people · 3 lanes · 4 milestones
**Status:** Step 1 shipped; Step 2 in build
**Stack:** React 18 + Vite + TypeScript + Tailwind · pywhispercpp (whisper.cpp) · FastAPI · pyannote-audio (stretch)

---

## 0. What changed in v1.2

Building Step 1 surfaced two decisions worth changing in v1.1:

| Topic | v1.1 | v1.2 |
|---|---|---|
| Frontend | Angular + TS | **React 18 + Vite + TS + Tailwind** — faster path to the Vision-UI-inspired dashboard aesthetic; no Angular dark-theme kit matches the supplied reference. The PRD architecture (FastAPI bridge, WS, HTTPS POST) is unchanged. |
| STT integration | whisper.cpp as a C++ subprocess | **pywhispercpp** — bundles the same whisper.cpp binary, loads the model once in-process, avoids per-chunk subprocess overhead. Required Python 3.10+. |
| Roadmap scope | LLM was out of scope | LLM is now **Step 3** in the roadmap (see §9). Hackathon target expanded after the brief evolved. |

## What changed from v0.2 → v1.0

| Topic | v0.2 assumption | v1.0 (official) |
|---|---|---|
| Frontend | Next.js | Angular (later revised to React in v1.2) |
| STT engine | faster-whisper (Python) | **whisper.cpp** (now via pywhispercpp wrapper in v1.2) |
| Backend | Next.js API routes | **FastAPI** (Python) |
| LLM extraction | Ollama / Mistral local | Out of scope (revised in v1.2: now Step 3) |
| Delivery endpoint | export JSON only | **POST to `staging.doings.de/stt`** |
| Approve/reject UI | in scope | Step 3 (LLM analysis ships with approve/reject cards) |
| Packaging | none | **PyInstaller .exe** (stretch) / **Electron** (stretch) |

The hackathon scope through Step 2 is: **Capture → STT → Fan-out**. Steps 3–4 layer local LLM analysis and structured-requirement generation on top.

---

## 1. Problem

Meeting tools are cloud-bound. Audio leaves the laptop, transcripts arrive late, and the structured
insight engineering teams need is never in the export. For Telekom, Siemens, and Volkswagen —
the target audience — this is a hard blocker: internal conversations cannot touch third-party clouds.

**What they want instead:** Local STT that the team owns. A stream they control.
Text leaves the machine only over one configurable HTTPS endpoint, on their terms.

---

## 2. Goal

Build a local meeting assistant with three guarantees:

1. **Audio never leaves the device.** whisper.cpp runs fully on-device, offline-capable.
2. **Transcript appears as you talk.** Chunked, rolling transcription — not a post-meeting summary.
3. **Every segment is delivered.** Fanned out to both the local Angular UI and `staging.doings.de/stt`.

**Demo success:** a live meeting is transcribed in German and English, appears word-by-word in the
Angular UI, and each segment is confirmed delivered to the Doings staging endpoint.

---

## 3. Scope

### Core MVP — the demo cannot happen without these

- Local multilingual transcription (German + English, auto-detected per segment)
- HTTPS POST to `staging.doings.de/stt` for every segment
- Offline STT — no network required for capture or transcription
- System audio capture (OS-native, per platform)

### Stretch — nice to have by the final milestone

- Near-real-time speaker attribution (pyannote-audio as delayed annotation layer)
- PyInstaller-built Windows `.exe`
- Electron packaging of the Angular shell
- macOS system audio via ScreenCaptureKit Swift helper

### Explicitly out of scope

- LLM-based requirement extraction (Doings' downstream pipeline handles this)
- Approve / reject UI for extracted items
- Cloud ASR of any kind
- Multi-user collaborative view
- Authentication or persistent storage

---

## 4. Target audience

**Telekom · Siemens · Volkswagen** — large German engineering orgs in regulated industries.

Every architectural decision flows from this:
- Raw audio must never leave the device
- Offline operation is required (secure on-site facilities)
- German is a first-class language — not an afterthought
- The HTTPS endpoint must be swappable per environment (staging → prod) without touching the pipeline

---

## 5. Architecture — five components, one local app

Each component is an isolated process. The demo still works if a stretch component (diarization)
breaks. This is intentional — modular by design.

```
┌─────────────────────────────────────────────────────────────────┐
│                        LOCAL MACHINE                            │
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │  02 Capture  │────►│  03 whisper  │────►│  04 FastAPI    │  │
│  │   service    │ PCM │    .cpp      │segs │  fan-out       │  │
│  │              │/WAV │  worker      │     │                │  │
│  │ PyAudioWPatch│     │              │     │                │  │
│  │ ScreenCapture│     │ Multilingual │     │                │  │
│  │    Kit*      │     │ Timestamped  │     │                │  │
│  └──────────────┘     └──────────────┘     └───────┬────────┘  │
│                                                    │           │
│                       ┌──────────────┐             │           │
│                       │  05 Diariz.  │ (stretch)   │           │
│                       │   worker     │─────────────┤           │
│                       │ pyannote-    │  speaker     │           │
│                       │   audio      │  labels      │           │
│                       └──────────────┘             │           │
│                                                    │           │
│  ┌─────────────────────────────────────────────┐   │           │
│  │  01 Angular UI                              │◄──┘ local WS  │
│  │  Live transcript · Delivery status          │               │
│  │  Session controls · Speaker chips (later)   │               │
│  └─────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS POST (text only)
                                ▼
                    staging.doings.de/stt
```

---

## 6. Component specifications

### 01 — React UI
**Tech:** React 18 · Vite · TypeScript · Tailwind CSS
**Style:** Vision-UI-inspired dark/glassy aesthetic (see [docs/superpowers/specs/2026-05-18-step2-web-ui-design.md](docs/superpowers/specs/2026-05-18-step2-web-ui-design.md) for the full design)
**Runs:** localhost, browser (Electron shell as stretch)

Responsibilities:
- Live transcript stream — segments appear as they arrive over WebSocket from FastAPI
- Delivery status panel — shows confirmed / pending / failed for each segment's HTTPS POST
- AI insights panel — placeholder in Step 2; populated by Step 3's LLM extraction
- Session controls — Start, Stop, Export session as JSON. Start/Stop hit `POST /control/*` on the backend, which spawns/SIGINTs the capture subprocess.
- Inline transcript editing — deferred (originally PRD scope; not demo-critical)
- Speaker chips — appear when diarization annotates a segment (stretch, non-blocking)

Layout (3-column on desktop, stacks on narrow viewports):
```
┌──────────────────────────────────────────────────────────────────────┐
│  ● Recording  00:14:32   Segments: 47   Delivered: 46/47   [▶][■][↓] │
├──────────────────────┬───────────────────────┬───────────────────────┤
│  LIVE TRANSCRIPT     │  DELIVERY STATUS      │  AI INSIGHTS          │
│  (col-span 6)        │  (col-span 3)         │  (col-span 3)         │
│                      │                       │                       │
│  [00:12.4] [DE]      │  seg-047  ✓           │   Step 3 placeholder  │
│  Das System muss...  │  seg-046  ✓           │                       │
│                      │  seg-045  ⟳           │                       │
│  [00:17.0] [EN]      │  seg-044  ✓           │                       │
├─────────────────────────┴────────────────────────────────┤
│  [Start]  [Stop]  [Export]                               │
└──────────────────────────────────────────────────────────┘
```

### 02 — Capture service
**Tech:** PyAudioWPatch (Windows WASAPI) · ScreenCaptureKit Swift helper (macOS, stretch)
**Runs:** Python subprocess

Responsibilities:
- Mic input: standard capture on all platforms (guaranteed path)
- System/loopback audio: WASAPI loopback on Windows (bonus path), ScreenCaptureKit on macOS (stretch)
- Normalize output to PCM/WAV chunks of 1–2 seconds with ~200ms overlap
- Feed chunks to whisper.cpp worker over a local queue or pipe

**Mic is the contract.** System audio is the bonus. Never block the demo on loopback capture.

### 03 — Transcription worker
**Tech:** `pywhispercpp` (Python bindings bundling the whisper.cpp binary)
**Runs:** in-process inside the capture service, Metal-accelerated on Apple Silicon, no network

Responsibilities:
- Consume PCM/WAV chunks from the capture service
- Run multilingual Whisper model — language auto-detected per segment
- Return timestamped segments with confidence scores
- No network, no upload, no quota — fully offline

Model recommendation:

| Model | Size | Speed | German quality | Use when |
|---|---|---|---|---|
| `ggml-small` | 244MB | Fast | Good | Default demo choice |
| `ggml-medium` | 769MB | Moderate | Strong | If German accuracy is poor |
| `ggml-large-v3` | 1.5GB | Slow | Best | Stretch / GPU available |

Start with `ggml-small`. Switch to `ggml-medium` only if German is mangled in testing.

Segment output schema:
```json
{
  "id": "seg-047",
  "session_id": "sess-20260519-001",
  "text": "Das System muss mindestens 500 gleichzeitige Nutzer unterstützen.",
  "start_ms": 12400,
  "end_ms": 15100,
  "lang": "de",
  "confidence": 0.91
}
```

Timestamps are mandatory on every segment — they are the foundation for future diarization merging.

### 04 — Delivery service (FastAPI fan-out)
**Tech:** FastAPI · httpx · WebSocket
**Runs:** Python, localhost

Responsibilities:
- Receive completed segments from the transcription worker
- Fan out to two destinations simultaneously:
  - **Local:** push to Angular UI over WebSocket (`ws://localhost`)
  - **Remote:** HTTP POST to `staging.doings.de/stt`
- Retry on 5xx responses from the remote endpoint (exponential backoff, max 3 retries)
- Report delivery status back to the Angular UI (confirmed / retrying / failed)

POST payload to `staging.doings.de/stt`:
```
POST /stt
Content-Type: application/json

{
  "text": "Das System muss mindestens 500 gleichzeitige Nutzer unterstützen.",
  "start_ms": 12400,
  "end_ms": 15100,
  "lang": "de",
  "session_id": "sess-20260519-001"
}
```

The endpoint URL is configurable via environment variable — swapping staging → prod
requires no code change.

### 05 — Diarization worker (stretch)
**Tech:** pyannote-audio
**Runs:** Python subprocess, optional — demo works without it

Responsibilities:
- Run on the same WAV audio in parallel, a few seconds behind the live transcript
- Produce speaker segments with start/end times (`Speaker 1`, `Speaker 2`, …)
- Deliver speaker labels to FastAPI, which patches existing transcript segments in the Angular UI
- Speaker chips appear in the UI when ready — never blocking or replacing transcript lines

**This component must never be a demo dependency.** If it crashes, the session continues normally.

---

## 7. Key technical decisions

**React + localhost, not a cloud app.** The same React + Vite + Tailwind code runs in a browser
today and wraps into an Electron shell later — without touching the capture or backend processes.
This is the migration path to a packaged desktop app.

**whisper.cpp via pywhispercpp.** The C++ implementation is faster on CPU and Metal-accelerated on
Apple Silicon. Wrapping it with pywhispercpp lets us load the model once in-process (no per-chunk
subprocess overhead) while still being the right foundation for a PyInstaller-packaged `.exe`.

**Mic is the guaranteed path.** System audio capture is OS-specific and fragile. The demo
is built around mic input. Loopback audio is a bonus added only after mic path is solid.

**Diarization is decoration, not infrastructure.** It runs as a delayed annotation — never
in the hot path. The transcript is already good without it.

**One configurable endpoint.** `staging.doings.de/stt` is set via environment variable.
Pointing at prod, a mock, or a different vendor requires no code change.

---

## 8. Team lanes

Three people, three lanes — blockers in one lane don't cascade to others.

### Person 01 — React UI
- Vite + React + TS + Tailwind shell with the Vision-UI-inspired dark/glassy style
- Live transcript view (WebSocket consumer)
- Delivery status panel
- AI insights panel (placeholder in Step 2; populated in Step 3)
- Session controls: Start / Stop / Export — Start/Stop hit `POST /control/*` on the backend
- Speaker chips (stretch)

### Person 02 — Capture + STT
- Audio capture helper (mic first, loopback second)
- Chunk normalization with 200ms overlap
- pywhispercpp integration (model loaded once in-process)
- `--api-url` flag: POST each Segment to the backend
- Stable `seg-NNN` IDs + `session_id` per run

### Person 03 — Backend + Delivery
- FastAPI skeleton, WebSocket server, control endpoints
- `POST /control/start` / `stop` — manages the capture subprocess lifecycle
- HTTPS forwarder to `staging.doings.de/stt` (env-configurable `DOINGS_ENDPOINT`)
- Retry logic and per-segment delivery status events over WS
- Diarization merge into transcript segments (stretch)

---

## 9. Product Roadmap

The product is built in four sequential steps. Each step is a fully working, demoable product on
its own — never a half-finished feature. Do not start a step until the previous one works end-to-end.

```
STEP 1          STEP 2          STEP 3          STEP 4
────────        ────────        ────────        ────────
Terminal        Beautiful       Local LLM       Requirements
live STT    ──► Web UI      ──► Analysis    ──► & Tickets

Mic → text      Angular UI      Mistral/        Structured
in terminal     live stream     Phi-3 local     JSON → Doings
                                approve/reject  pipeline
```

---

### Step 1 — Terminal Live STT ✦ MVP
*"Speak into the mic. See text in the terminal. Nothing else."*

This is the non-negotiable foundation. Everything else depends on it working cleanly.

**What it does:**
- Captures mic audio continuously in 1–2 second PCM chunks
- Passes each chunk to whisper.cpp running locally
- Prints each transcript segment to terminal with timestamp and detected language
- Runs fully offline — no network, no API keys

**Done when:** You speak a sentence in German, then one in English, and both appear
correctly transcribed in the terminal within ~3 seconds of being spoken.

**Deliverables:**
- [ ] Mic audio captured and chunked (`sounddevice` or `pyaudio`)
- [ ] whisper.cpp binary built and `ggml-small` model downloaded
- [ ] Python script wiring mic → whisper.cpp → stdout
- [ ] Timestamps on every segment (`start_ms`, `end_ms`)
- [ ] Language auto-detection working (DE + EN in same session)

**Terminal output format:**
```
[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen.
[00:17.0 → 00:19.3] [EN] Authentication should use OAuth 2.0.
[00:21.1 → 00:24.8] [DE] Ja, and it must also work offline.
```

**Tech:** Python · whisper.cpp · sounddevice · numpy

---

### Step 2 — Beautiful Web UI
*"The same live transcript, now in a polished Angular interface."*

Take the working terminal output from Step 1 and stream it into a well-designed browser UI.
The pipeline doesn't change — just add a FastAPI bridge and the Angular frontend.

**What it does:**
- FastAPI server receives segments from the Python STT process (local POST or queue)
- Fans out to two destinations: Angular UI (WebSocket) and `staging.doings.de/stt` (HTTPS POST)
- Angular shows a live, auto-scrolling transcript with timestamps and language badges
- Delivery status panel confirms each segment was received by the Doings endpoint
- Inline editing — click any segment to correct a transcription error during the meeting
- Session controls: Start, Stop, Export JSON

**Done when:** Speaking into the mic produces live text in the browser within 3–5 seconds,
and the delivery status panel shows each segment confirmed to `staging.doings.de/stt`.

**Deliverables:**
- [ ] FastAPI server with WebSocket endpoint and HTTPS forwarder
- [ ] Angular app consuming WebSocket and rendering transcript feed
- [ ] Language badges (DE / EN) and timestamps on each segment card
- [ ] Delivery status panel (confirmed ✓ / retrying ⟳ / failed ✗)
- [ ] Inline segment editing (click to correct)
- [ ] Start / Stop / Export session controls
- [ ] Auto-scroll with manual pause toggle
- [ ] Retry logic on 5xx from remote endpoint (exponential backoff, max 3 retries)

**UI layout:**
```
┌──────────────────────────────────────────────────────────┐
│  ● Recording  00:14:32   Segments: 47   Delivered: 46    │
├─────────────────────────┬────────────────────────────────┤
│  LIVE TRANSCRIPT        │  DELIVERY STATUS               │
│                         │                                │
│  [00:12.4] [DE]         │  seg-047  ✓ delivered          │
│  Das System muss...     │  seg-046  ✓ delivered          │
│                         │  seg-045  ⟳ retrying...        │
│  [00:17.0] [EN]         │  seg-044  ✓ delivered          │
│  Auth should use        │                                │
│  OAuth 2.0              │                                │
│                         │                                │
│  [editing...]           │                                │
├─────────────────────────┴────────────────────────────────┤
│  [▶ Start]  [■ Stop]  [↓ Export]                         │
└──────────────────────────────────────────────────────────┘
```

**Tech:** Angular · TypeScript · FastAPI · httpx · WebSocket

---

### Step 3 — Local LLM Analysis
*"The transcript is now understood, not just captured."*

Add a local language model that reads each transcript segment and classifies it — requirement,
action item, decision, or chatter. The user can approve or reject each extracted item
directly in the UI, during the meeting.

**What it does:**
- Each finalized transcript segment is passed to a local LLM (Mistral or Phi-3 via Ollama)
- LLM classifies the segment and returns a structured JSON item
- Extracted items appear as cards in a new right-hand panel alongside the transcript
- User approves ✓ or rejects ✗ each card inline — no batch processing after the meeting
- Approved items are stored in session state; rejected items are dismissed
- Low-confidence extractions are flagged for review rather than auto-approved

**Done when:** Speaking a requirement in German or English produces a structured card
in the UI within ~8 seconds, which the user can approve or reject with one click.

**Deliverables:**
- [ ] Ollama running locally with `mistral` or `phi3` model pulled
- [ ] Extraction prompt with structured JSON output schema (see below)
- [ ] Angular right-hand panel showing extracted item cards
- [ ] Approve / reject interaction per card
- [ ] Confidence indicator on each card
- [ ] Rolling context window — LLM sees last 60 seconds of transcript, not just current segment
- [ ] Conservative defaults — classify as chatter when uncertain

**Extraction output schema:**
```json
{
  "type": "requirement" | "action_item" | "decision" | "chatter",
  "text": "Cleaned, normalized statement in the original language",
  "confidence": 0.0–1.0,
  "language": "en" | "de",
  "source_quote": "Exact words from the transcript segment",
  "needs_review": true | false
}
```

**LLM setup:**
```bash
ollama pull mistral        # ~4GB, strong German + instruction following
# or
ollama pull phi3           # ~2.4GB, lighter — better for limited RAM
ollama serve               # exposes REST API at localhost:11434
```

**Tech:** Ollama · Mistral 7B or Phi-3-mini · FastAPI LLM proxy · Angular card components

---

### Step 4 — Requirements & Tickets ✦ Big Final Step
*"Approved items become engineering artifacts."*

Convert the session's approved extractions into properly structured requirements and
actionable tickets, then POST them to Doings.ai's pipeline for downstream processing.
This is the full-circle moment: spoken meeting → structured spec → engineering backlog.

**What it does:**
- All approved items from Step 3 are collected into a session summary
- A final LLM pass normalizes and enriches them: assigns IDs, types, priorities, and links
  related items (e.g. a decision that constrains a requirement)
- Output is a structured requirements document conforming to Doings.ai's internal schema
- Each requirement is also formatted as a ticket-ready payload (title, description, acceptance criteria)
- The full document is POSTed to `staging.doings.de/stt` (or a separate Doings ingest endpoint)
- The Angular UI shows a "Requirements" view alongside the live transcript — the final deliverable
  of the session, ready to export or hand off

**Done when:** At the end of a simulated meeting, clicking "Generate Requirements" produces
a clean list of numbered requirements and draft tickets, correctly in German or English,
that Doings.ai's team can recognise as valid input to their pipeline.

**Deliverables:**
- [ ] Session summary collector — aggregates all approved items
- [ ] Final LLM enrichment pass (IDs, priority, type, linked items)
- [ ] Requirements document conforming to Doings.ai's schema
- [ ] Ticket payload generation (title, description, acceptance criteria per item)
- [ ] POST to Doings ingest endpoint with retry
- [ ] "Requirements" view in Angular UI — clean, exportable list
- [ ] Export as JSON and (stretch) markdown or PDF
- [ ] Pre-recorded DE/EN fallback demo clip covering all four steps
- [ ] Full live demo rehearsed at least twice

**Requirements document schema:**
```json
{
  "session": {
    "id": "sess-20260519-001",
    "started_at": "2026-05-19T09:00:00Z",
    "duration_seconds": 1421,
    "language": "de+en"
  },
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Concurrent user capacity",
      "text": "The system must support at least 500 concurrent users.",
      "type": "functional",
      "priority": "high",
      "language": "en",
      "source_quote": "Das System muss mindestens 500 Nutzer unterstützen.",
      "timestamp_start": 12400,
      "timestamp_end": 15100,
      "status": "approved",
      "human_verified": true,
      "linked_items": []
    }
  ],
  "tickets": [
    {
      "requirement_id": "REQ-001",
      "title": "Implement concurrent user support (500+)",
      "description": "Ensure the system architecture supports at least 500 simultaneous users.",
      "acceptance_criteria": [
        "Load test passes at 500 concurrent users",
        "Response time stays under 2s at peak load"
      ]
    }
  ]
}
```

**Tech:** Ollama · FastAPI enrichment endpoint · Angular requirements view · Doings ingest API

---

### Roadmap summary

| Step | Name | Output | Demoable alone |
|---|---|---|---|
| 1 | Terminal Live STT | Text in terminal | ✅ Yes |
| 2 | Beautiful Web UI | Live transcript in browser + delivery | ✅ Yes |
| 3 | Local LLM Analysis | Approve/reject extracted items live | ✅ Yes |
| 4 | Requirements & Tickets | Structured spec + tickets → Doings pipeline | ✅ Yes |

**Hard rule:** each step must work end-to-end before the next begins.
A working Step 1 with nothing else is a better demo than a broken Step 3.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| whisper.cpp slow on demo CPU (no GPU) | Use `ggml-small`; test on actual demo hardware in M1 |
| German accuracy poor on small model | Switch to `ggml-medium` early; test with DE sample audio in M1 |
| System audio loopback fragile | Mic is the contract — build and demo on mic first |
| `staging.doings.de/stt` endpoint unavailable | Mock it locally with a FastAPI echo server during development |
| Diarization blocks demo | It's a separate optional process — demo works without it by design |
| Angular ↔ FastAPI WS breaks | Wire and test this pipe in M1 before any UI work |
| Live demo audio fails | Pre-recorded DE/EN fallback clip, tested end-to-end before showtime |
| whisper.cpp subprocess management tricky | Wrap in a simple Python class; test WAV→transcript in isolation first |

---

## 11. Local dev setup (quick start)

```bash
# 1. Clone whisper.cpp and build
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp && make
bash ./models/download-ggml-model.sh small   # 244MB

# 2. Python environment (capture + FastAPI)
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn httpx pyaudio sounddevice numpy pyannote.audio

# 3. Angular UI
npm install -g @angular/cli
ng new meeting-ui --standalone && cd meeting-ui
npm install

# 4. Run all three processes
python capture_service.py      # terminal 1
python fastapi_server.py       # terminal 2
ng serve                       # terminal 3
```

---

## 12. Open questions

- Can Doings share the expected request schema for `staging.doings.de/stt`? *(Confirm field names before building the POST)*
- What hardware does the demo laptop have — CPU only or GPU? *(Determines safe model size)*
- Is the staging endpoint live and accepting test POSTs today? *(Mock it if not)*
- Should the Angular UI be in German, English, or both?
- Any specific domain vocabulary (acronyms, product names) to add as Whisper prompt hints?
