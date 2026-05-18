# CLAUDE.md — Local Meeting Intelligence (Doings.ai × CF Hackathon 2026)

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD. This file is the working brief for Claude.

## What we're building

A **local** meeting assistant: mic audio → on-device STT → live transcript in a React dashboard + HTTPS POST to `staging.doings.de/stt`. Audio never leaves the device. German + English, auto-detected (or forced).

Scope expands step-by-step (see Build order below). Step 1 is shipped; Step 2 (Web UI) is in progress; Steps 3–4 follow.

## Stack (locked)

- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS — Vision-UI-inspired dark/glassy aesthetic, no component library. (Earlier PRD draft said Angular; superseded — see PRD §0.)
- **STT:** whisper.cpp via `pywhispercpp` (loads model once in-process). Default model `ggml-medium`; works on Apple Silicon with Metal.
- **Backend:** FastAPI (Python) + httpx (async) + WebSocket
- **Capture:** `sounddevice` for mic (Windows: PyAudioWPatch loopback; macOS: ScreenCaptureKit — both stretch)
- **Diarization (stretch):** pyannote-audio
- **Delivery target:** `staging.doings.de/stt` — endpoint URL is env-var configurable (`DOINGS_ENDPOINT`)
- **Python:** 3.10+ required (pywhispercpp uses PEP 604 unions). Step 1 dev is on 3.14.

Do NOT substitute: no cloud ASR, no auth, no persistent storage, no Next.js, no faster-whisper.

## Architecture (after Step 2)

Three local processes:

1. **`capture/` — Python STT** (Step 1, shipped). Mic → 2s+200ms-overlap chunks → pywhispercpp → POST each Segment to `backend/`. Can run standalone (prints to stdout) or be spawned by `backend/`.
2. **`backend/` — FastAPI fan-out** (Step 2). Receives segments, broadcasts over WebSocket to UI, retries HTTPS POST to `staging.doings.de/stt`, manages the capture subprocess (Start/Stop from UI).
3. **`ui/` — React dashboard** (Step 2). Live transcript + delivery status + AI insights placeholder (filled in Step 3). Dark/glassy, three-column layout.

PRD-stretch components (diarization worker, system audio loopback) attach later without changing this trio.

## Transcript shaping

Default Step 1 output is **one line per raw whisper segment**. An experimental paragraph aggregator (`--paragraphs`) groups consecutive segments by silence gap, language change, or max duration, but accuracy of the boundary heuristic still needs work — keep it opt-in until line-by-line is reliable. Speaker- and topic-based grouping are separate concerns (PRD diarization stretch and Step 3 LLM analysis, respectively).

## Build order (hard rule)

Each step must work end-to-end before the next begins. A working Step 1 alone beats a broken Step 3.

1. **Terminal Live STT** ✅ — mic → whisper.cpp → stdout `[mm:ss.s → mm:ss.s] [DE/EN] text`
2. **Beautiful Web UI** 🚧 — FastAPI bridge + React dashboard + delivery to `staging.doings.de/stt` + Start/Stop from UI
3. **Local LLM Analysis** — Ollama (mistral/phi3) classifies segments; approve/reject cards in the insights panel
4. **Requirements & Tickets** — aggregate approved items → structured spec → Doings ingest

## Segment schema

Internally we work in seconds (`start_s`, `end_s`). The PRD's outbound POST uses milliseconds; convert at the delivery boundary.

**Internal (capture ↔ backend ↔ UI):**
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

**Outbound POST to `staging.doings.de/stt`:**
```json
{ "text": "...", "start_ms": 12400, "end_ms": 15100, "lang": "de", "session_id": "..." }
```

## WebSocket message types (backend → UI)

```json
{"type": "segment",  "segment": { ...Segment... }}
{"type": "delivery", "id": "seg-047", "status": "pending|delivered|failed", "attempts": 1}
{"type": "state",    "state": "idle|recording|stopping", "session_id": "..."}
```

## Non-negotiables

- **Audio never leaves the device.** STT is fully on-device, offline-capable.
- **Mic is the contract.** System/loopback audio is a bonus — never block the demo on it.
- **Diarization is decoration.** If it crashes, the session keeps running.
- **One configurable endpoint.** Staging → prod swap is an env var, not a code change.
- **German is first-class**, not an afterthought. Target: Telekom / Siemens / Volkswagen.
- **Modular processes.** A failure in one component must not cascade.
- **Line-by-line transcript is the default.** Paragraph grouping is opt-in (`--paragraphs`) until accurate.

## Team lanes

- **P01:** UI (React dashboard — transcript, delivery, insights placeholder, Start/Stop controls)
- **P02:** Capture + STT (Step 1 shipped; Step 2 adds `--api-url` flag + stable IDs)
- **P03:** Backend + Delivery (FastAPI, WS broadcast, HTTPS forwarder with retry, subprocess control)

## Out of scope (don't build in current step)

- LLM extraction (Step 3)
- Approve/reject UI (Step 3)
- Inline transcript editing (defer)
- Cloud ASR of any kind
- Multi-user views, auth, persistent storage (full project)
- Frontend unit tests (Step 2; manual acceptance is enough at hackathon scope)

## Open questions (confirm before assuming)

- Exact request schema expected by `staging.doings.de/stt` (we currently send `text/start_ms/end_ms/lang/session_id`)
- Demo hardware (CPU only vs GPU) — determines safe model size
- Is staging endpoint live today? If not, mock with a local FastAPI echo (`uvicorn echo:app --port 8001`, then set `DOINGS_ENDPOINT=http://localhost:8001/stt`)
- UI language: DE, EN, or both
- Domain vocabulary for Whisper prompt hints
