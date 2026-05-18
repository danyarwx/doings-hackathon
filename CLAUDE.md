# CLAUDE.md — Local Meeting Intelligence (Doings.ai × CF Hackathon 2026)

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD. This file is the working brief for Claude.

## What we're building

A **local** meeting assistant: mic audio → on-device STT → live transcript in Angular UI + HTTPS POST to `staging.doings.de/stt`. Audio never leaves the device. German + English, auto-detected.

Scope is strictly **Capture → STT → Fan-out**. Structured extraction (LLM) and approve/reject UI come in later roadmap steps; they are NOT v1.

## Stack (locked)

- **Frontend:** Angular + TypeScript (localhost; Electron later)
- **STT:** whisper.cpp (C++ subprocess) with `ggml-small` (switch to `ggml-medium` only if German is mangled)
- **Backend:** FastAPI (Python) + httpx + WebSocket
- **Capture:** `sounddevice`/`pyaudio` for mic (Windows: PyAudioWPatch loopback; macOS: ScreenCaptureKit — both stretch)
- **Diarization (stretch):** pyannote-audio
- **Delivery target:** `staging.doings.de/stt` — endpoint URL must be env-var configurable

Do NOT substitute: no Next.js, no faster-whisper, no cloud ASR, no auth, no persistent storage.

## Architecture

Five isolated processes, one local app:

1. **Angular UI** — live transcript (WS), delivery status panel, Start/Stop/Export, inline edit
2. **Capture service** — mic → 1–2s PCM/WAV chunks with ~200ms overlap → queue
3. **whisper.cpp worker** — chunks → timestamped multilingual segments
4. **FastAPI fan-out** — segments → WS (UI) + HTTPS POST (staging.doings.de/stt) with retry (exp backoff, max 3, on 5xx)
5. **Diarization worker (stretch)** — pyannote labels patched onto existing segments; never on hot path

## Build order (hard rule)

Each step must work end-to-end before the next begins. A working Step 1 alone beats a broken Step 3.

1. **Terminal Live STT** — mic → whisper.cpp → stdout with `[mm:ss.s → mm:ss.s] [DE/EN] text`
2. **Beautiful Web UI** — add FastAPI bridge + Angular live view + delivery to staging.doings.de/stt
3. **Local LLM Analysis** — Ollama (mistral/phi3) classifies segments; approve/reject cards
4. **Requirements & Tickets** — aggregate approved items → structured spec → Doings ingest

## Segment schema (transcription worker → fan-out)

```json
{
  "id": "seg-047",
  "session_id": "sess-20260519-001",
  "text": "...",
  "start_ms": 12400,
  "end_ms": 15100,
  "lang": "de",
  "confidence": 0.91
}
```

Timestamps are mandatory — they're the join key for diarization later.

## POST payload (fan-out → staging.doings.de/stt)

```json
{ "text": "...", "start_ms": 12400, "end_ms": 15100, "lang": "de", "session_id": "..." }
```

## Non-negotiables

- **Audio never leaves the device.** STT is fully on-device, offline-capable.
- **Mic is the contract.** System/loopback audio is a bonus — never block the demo on it.
- **Diarization is decoration.** If it crashes, the session keeps running.
- **One configurable endpoint.** Staging → prod swap is an env var, not a code change.
- **German is first-class**, not an afterthought. Target: Telekom / Siemens / Volkswagen.
- **Modular processes.** A failure in one component must not cascade.

## Team lanes

- **P01:** Angular UI (transcript, delivery panel, controls, inline edit, speaker chips stretch)
- **P02:** Capture + STT (mic capture, chunking, whisper.cpp subprocess, timestamped API)
- **P03:** Backend + Delivery (FastAPI, WS, HTTPS forwarder, retry, diarization merge stretch)

## Out of scope (don't build)

LLM extraction in v1 (it's Step 3+), approve/reject UI in v1, cloud ASR of any kind, multi-user views, auth, persistent storage.

## Open questions (confirm before assuming)

- Exact request schema expected by `staging.doings.de/stt`
- Demo hardware (CPU only vs GPU) — determines safe model size
- Is staging endpoint live today? If not, mock with a local FastAPI echo
- UI language: DE, EN, or both
- Domain vocabulary for Whisper prompt hints
