# CLAUDE.md — Local Meeting Intelligence (Doings.ai × CF Hackathon 2026)

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD. This file is the working brief for Claude.

## What we're building

A **local** meeting assistant: mic audio → on-device STT → live transcript in a React dashboard + HTTPS POST to `staging.doings.de/stt`. Audio never leaves the device. German + English, auto-detected (or forced). Local LLM (Ollama) extracts requirement candidates live; user approves / edits / declines them.

Scope expands step-by-step (see Build order below). Steps 1–3 are shipped; Step 4 (structured Jira-ready export) is next.

## Stack (locked)

- **Frontend:** React 19 + Vite + TypeScript + Tailwind CSS + framer-motion + lucide-react — Vision-UI-inspired dark/glassy aesthetic, no component library. (Earlier PRD draft said Angular; superseded — see PRD §0.)
- **STT:** whisper.cpp via `pywhispercpp` (loads model once in-process). Default model `ggml-medium`; works on Apple Silicon with Metal.
- **LLM (Step 3):** Ollama running locally, default model `phi3`; `mistral` and `llama3.1` are alternatives, live-swappable from the UI.
- **Backend:** FastAPI (Python) + httpx (async) + WebSocket
- **Capture:** `sounddevice` for mic (Windows: PyAudioWPatch loopback; macOS: ScreenCaptureKit — both stretch)
- **Diarization (stretch):** pyannote-audio
- **Delivery target:** `staging.doings.de/stt` — endpoint URL is env-var configurable (`DOINGS_ENDPOINT`)
- **Python:** 3.10+ required (pywhispercpp uses PEP 604 unions). Dev is on 3.14.

Do NOT substitute: no cloud ASR, no cloud LLM, no auth, no persistent storage, no Next.js, no faster-whisper.

## Architecture (current)

Three local processes plus optional Ollama:

1. **`capture/` — Python STT** (Step 1, shipped). Mic → 2s+200ms-overlap chunks → pywhispercpp → POST each Segment to `backend/`. Can run standalone (prints to stdout) or be spawned by `backend/`. Accepts `--prompt <vocabulary>` for whisper hint biasing.
2. **`backend/` — FastAPI fan-out** (Step 2 + 3, shipped). Receives segments, broadcasts over WebSocket to UI, retries HTTPS POST to `staging.doings.de/stt`, manages the capture subprocess (Start/Pause/Stop from UI). Houses the `SentenceBuffer` (aggregates whisper fragments into `Utterance`s) and the event-driven `ExtractorWorker` that calls Ollama and broadcasts `Insight` cards.
3. **`ui/` — React dashboard** (Step 2 + 3, shipped). Top nav (History, Vocabulary, Model picker, Export-stub) + Live Transcript + AI Insights panels. Dark/glassy, `max-w-7xl` centered.
4. **Ollama** (Step 3, optional but recommended). HTTP API at `localhost:11434`. The extractor calls it; if it's down the panel shows "AI offline" and the rest of the dashboard keeps working.

PRD-stretch components (diarization worker, system audio loopback) attach without changing this trio.

## SentenceBuffer + ExtractorWorker contract (Step 3)

- Whisper emits ~2s segments. The `SentenceBuffer` does NOT flush on terminal punctuation (whisper adds `.` at every chunk boundary, so it isn't a real sentence signal). It flushes on **silence gap >1.5s** (`BUFFER_MAX_SILENCE_S`) or **20s hard cap** (`BUFFER_MAX_DURATION_S`). Blank-audio segments are dropped.
- Each flush emits one `Utterance` on an `asyncio.Queue`.
- The `ExtractorWorker` consumes the queue (no tick). For every utterance it builds a prompt with the **FOCUS** (just-flushed utterance) and **CONTEXT** (last 3 prior utterances; read-only, for pronoun resolution). Skip-if-busy: if a previous LLM call is in flight, the new utterance is dropped.
- Filter gates, in order: `is_requirement` → length ≥ `EXTRACTOR_MIN_TEXT_LEN` (40) → modal/intent verb regex (EN+DE) → source-quote fuzzy match against the FOCUS → fuzzy dedupe against pending+approved insights → schema sanity (`certainty` ∈ {explicit, implied}, `category` ∈ {functional, non_functional}).

## Transcript shaping

Default capture output is **one line per raw whisper segment** (the UI shows these in the Live Transcript panel). The Step-3 extractor sees the *aggregated* `Utterance`s, not raw segments. The experimental `--paragraphs` flag in `capture/` is a separate, opt-in transcript-rendering mode; speaker- and topic-based grouping are still PRD stretch items.

## Build order (hard rule)

Each step must work end-to-end before the next begins. A working Step 1 alone beats a broken Step 3.

1. **Terminal Live STT** ✅ — mic → whisper.cpp → stdout `[mm:ss.s] [DE/EN] text`
2. **Beautiful Web UI** ✅ — FastAPI bridge + React dashboard + delivery to `staging.doings.de/stt` + Start/Pause/Stop from UI + History
3. **Local LLM Analysis** ✅ — Ollama-driven extractor, SentenceBuffer + event-driven worker, FOCUS+CONTEXT prompt, gated filter, Approve / Edit / Decline cards in the UI. Live model swap (phi3 / mistral / llama3.1) and vocabulary hint editing from the top nav.
4. **Requirements & Tickets** 🔲 — on Stop, take approved cards + full transcript through a richer LLM pass → Jira-ready JSON (user stories with Given/When/Then, acceptance criteria, INVEST validation, action items, decisions, topics) → Export view → Jira push.

## Segment + Utterance + Insight schemas

Internally we work in seconds (`start_s`, `end_s`). The PRD's outbound POST uses milliseconds; convert at the delivery boundary.

**Segment (capture ↔ backend ↔ UI):**
```json
{
  "id": "seg-047",
  "session_id": "sess-20260518-001",
  "text": "...",
  "start_s": 12.4,
  "end_s": 15.1,
  "lang": "de"
}
```

**Utterance (backend-internal, SentenceBuffer → ExtractorWorker):**
```json
{
  "text": "concatenated text spanning N segments",
  "start_s": 12.4,
  "end_s": 18.2,
  "lang": "de",
  "segment_ids": ["seg-047", "seg-048", "seg-049"]
}
```

**Insight (backend → UI):**
```json
{
  "id": "ins-003",
  "session_id": "sess-...",
  "category": "functional",
  "certainty": "explicit",
  "text": "The dashboard must show monthly revenue.",
  "original_text": "...",
  "source_quote": "...",
  "language": "en",
  "status": "pending",
  "created_at_iso": "2026-05-20T09:00:00Z"
}
```

**Outbound POST to `staging.doings.de/stt`:**
```json
{ "text": "...", "start_ms": 12400, "end_ms": 15100, "lang": "de", "session_id": "..." }
```

## WebSocket message types (backend → UI)

```json
{"type": "state",          "state": "idle|recording|paused|stopping", "session_id": "..."}
{"type": "segment",        "segment": { ...Segment... }}
{"type": "delivery",       "id": "seg-047", "status": "pending|delivered|failed", "attempts": 1}
{"type": "insight",        "insight": { ...Insight... }}
{"type": "insight_update", "id": "ins-003", "status": "approved|declined|pending", "text": "..."}
{"type": "ai_status",      "state": "ok|no_model|offline", "model": "phi3", "error": "..."}
```

## Backend HTTP routes (current)

- `POST /control/start { language? }` · `POST /control/pause` · `POST /control/stop`
- `POST /segments` (from capture)
- `GET /state` · `GET /healthz`
- `GET /history` · `GET /history/{session_id}` · `GET /session/export`
- `GET /insights` · `POST /insights/{id}/approve|decline|edit`
- `GET /ai/status`
- `GET /vocabulary` · `POST /vocabulary { text }` — whisper `--prompt` hint, applied on next ▶ Start
- `GET /model` · `POST /model { model }` — live-swap Ollama model (phi3 / mistral / llama3.1 / qwen2.5)
- `WS /ws` — fan-out

## Non-negotiables

- **Audio never leaves the device.** STT and LLM are fully on-device, offline-capable.
- **Mic is the contract.** System/loopback audio is a bonus — never block the demo on it.
- **Diarization is decoration.** If it crashes, the session keeps running.
- **One configurable endpoint.** Staging → prod swap is an env var, not a code change.
- **German is first-class**, not an afterthought. Target: Telekom / Siemens / Volkswagen.
- **Modular processes.** A failure in one component must not cascade. Ollama down → AI panel offline, transcript unaffected.
- **Line-by-line transcript is the default.** The extractor's aggregated `Utterance` is internal — the UI keeps showing raw segment lines.

## Team lanes

- **P01:** UI (React dashboard — top nav, transcript, insights, history, model + vocabulary controls)
- **P02:** Capture + STT (mic chunks, pywhispercpp, `--api-url` + `--prompt` flags, stable IDs)
- **P03:** Backend + Delivery + LLM extractor (FastAPI, WS broadcast, HTTPS forwarder with retry, subprocess control, SentenceBuffer + ExtractorWorker + Ollama client)

## Out of scope (don't build in current step)

- Structured Jira-ready post-meeting pass — that IS Step 4
- Cloud ASR or cloud LLM of any kind
- Multi-user views, auth, persistent storage
- Frontend unit tests (manual acceptance is the contract through Step 4)

## Open questions (confirm before assuming)

- Exact request schema expected by `staging.doings.de/stt` (we currently send `text/start_ms/end_ms/lang/session_id`)
- Demo hardware (CPU only vs GPU) — determines safe model size
- Is staging endpoint live today? If not, mock with a local FastAPI echo (`uvicorn backend.echo_endpoint:app --port 8001`, then set `DOINGS_ENDPOINT=http://localhost:8001/stt`)
- UI language: DE, EN, or both
- Step 4 target: Jira REST API directly, or via Doings ingest?
