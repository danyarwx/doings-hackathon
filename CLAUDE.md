# CLAUDE.md — Local Meeting Intelligence (Doings.ai × CF Hackathon 2026)

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD. This file is the working brief for Claude.

## What we're building

A **local-first** meeting assistant: mic audio → on-device STT → live transcript in a React dashboard + HTTPS POST to `staging.doings.de/stt`. Audio never leaves the device. German + English, auto-detected (or forced). Local LLM (Ollama) extracts requirement candidates live; user approves / edits / declines. After Stop, a richer post-meeting pass produces Jira-ready user stories that can be pushed straight into Jira Cloud.

All four roadmap steps are shipped. Branch: `step-1-terminal-stt` is the active integration branch.

## Stack (locked)

- **Frontend:** React 19 + Vite + TypeScript + Tailwind CSS + framer-motion + lucide-react + `class-variance-authority` (for GlassButton). Dark/glassy Vision-UI aesthetic, no component library.
- **STT:** whisper.cpp via `pywhispercpp` (loads model once in-process). Default model `ggml-medium`; Metal-accelerated on Apple Silicon. **Capture uses a VAD state machine** — dynamic chunking on silence / max duration, NOT fixed 2-second intervals.
- **LLM:**
  - **Local (default):** Ollama at `localhost:11434`. Live-swappable: `phi3`, `phi4-mini:3.8b`, `mistral`, `llama3.1`, `qwen3:8b`, `qwen2.5`.
  - **Cloud (opt-in for dev/A-B testing):** OpenAI `openai/gpt-4o-mini` · Anthropic `anthropic/claude-haiku-4-5`. Selecting a cloud model breaks the local-only audio-never-leaves guarantee at the *transcript* level (audio still stays local); use only for benchmarking. The default config stays local.
- **Backend:** FastAPI (Python) + httpx (async) + WebSocket.
- **Capture:** `sounddevice` for mic (Windows: PyAudioWPatch loopback; macOS: ScreenCaptureKit — both stretch).
- **Jira integration:** REST API v3 with Basic auth (email + API token), ADF descriptions.
- **Diarization (stretch):** pyannote-audio.
- **Delivery target:** `staging.doings.de/stt` — endpoint URL is env-var configurable (`DOINGS_ENDPOINT`).
- **Python:** 3.10+ required (pywhispercpp uses PEP 604 unions). Dev is on 3.14.

Do NOT substitute: no cloud ASR, no auth, no persistent storage, no Next.js, no faster-whisper.

## Architecture (current)

```
┌────────────────────────────────────────────────────────────────────┐
│  capture/  Python · VAD state machine · pywhispercpp (whisper.cpp) │ ─┐
│    chunks audio dynamically on silence / 10s cap → POST /segments  │  │ stdout
│    Standalone mode prints transcripts to terminal.                 │  │ or
└────────────────────────────────────────────────────────────────────┘  │ subprocess
                                                                        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  backend/  FastAPI                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ SentenceBuffer  · noise-tag / silence-gap / 20s cap → Utterance      │  │
│  │ ExtractorWorker · queue-driven · FOCUS+CONTEXT prompt → LLMRouter    │  │
│  │ Filter gates    · length → verb regex → quote match → fuzzy dedupe   │  │
│  │ LLMRouter       · openai/ → OpenAI · anthropic/ → Anthropic · else → │  │
│  │                   Ollama                                              │  │
│  │ JiraClient      · ADF builder · Basic auth · POST /rest/api/3/issue  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  ◄ WebSocket /ws fan-out          ► HTTPS to staging.doings.de/stt          │
└────────────────────────────────────────────────────────────────────────────┘
                              │ WebSocket
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  ui/  React 19 + Vite + Tailwind                                   │
│  Pill nav: History · Vocabulary · Model picker · Export            │
│  Live Transcript │ AI Insights (Approve / Edit / Decline + detail) │
│  Past-session viewer  ·  Export view (edit + push to Jira)         │
└────────────────────────────────────────────────────────────────────┘
```

PRD-stretch components (diarization worker, system audio loopback) attach without changing this trio.

## VAD + SentenceBuffer + ExtractorWorker contract

**Capture (`capture/capture.py`):** RMS dBFS state machine.
- Recording starts when audio crosses `--vad-threshold` (default `-40 dBFS`).
- Keeps a 0.3s preroll so the first phoneme isn't clipped.
- Cuts the chunk on `--vad-silence` (default 0.5s) of dead air → natural phrase boundary.
- Forced cut at `--vad-max-duration` (default 10s) — keeps a 0.5s tail as overlap into the next chunk.
- Output to backend is `(start_s, audio_chunk)` per natural-phrase or capped chunk. Whisper sees full phrases, not 2s slices.

**Backend `SentenceBuffer`** (still useful even with VAD, because consecutive short utterances arrive back-to-back):
- Buffers segments. Flush triggers:
  1. Silence gap to next segment > `BUFFER_MAX_SILENCE_S` (default 1.5s) — the triggering segment starts the next buffer.
  2. Any **noise-only** segment arrives — `[BLANK_AUDIO]`, `(crowd chattering)`, `[music]`, `* sighs *`, anything wrapped entirely in `()`, `[]`, `*…*`. The noise segment itself is dropped.
  3. Total buffered duration ≥ `BUFFER_MAX_DURATION_S` (default 20s) — hard cap.
- **Punctuation does NOT trigger a flush.** Whisper emits `.` at every chunk boundary regardless of whether a sentence ended, so it's noise.
- `flush_pending()` is called on `/control/pause` and `/control/stop` so trailing speech reaches the LLM.

**`ExtractorWorker`** consumes the utterance queue (event-driven, no tick).
- For every utterance, builds a prompt with **FOCUS** (the new utterance) + **CONTEXT** (last 3 prior utterances, read-only for pronoun resolution).
- Skip-if-busy: if an LLM call is in flight, the new utterance is dropped (logged).
- Broadcasts `ai_status: thinking` before each call, `ok` after, `offline` on httpx error.
- Processes regardless of `recording_state` so the pause/stop flush still extracts.

**Filter gates** (in order):
1. **Length** — `text.strip() ≥ EXTRACTOR_MIN_TEXT_LEN` (default 30).
2. **Verb** — text must contain a modal or intent verb (regex). EN: must/shall/should/will/needs to/has to/have to + need/want/add/show/support/allow/integrate. DE: muss/müssen/müsste(n)/soll(en)/sollte(n)/wird/werden/werde/braucht/brauchen/möchte(n)/kann/können/könnte(n) + wollen/will/hinzufügen/zeigen/unterstützen/bereitstellen/integrieren/entwickeln/implementieren/bauen/bieten/erlauben/einführen/ermöglichen. Toggle with `EXTRACTOR_VERB_GATE`.
3. **Source quote** — must fuzzy-match the FOCUS utterance OR contain a 5+-word window that appears verbatim in FOCUS (handles small-model paraphrasing). Ratio default 0.6, `EXTRACTOR_QUOTE_MATCH_RATIO`.
4. **Fuzzy dedupe** — `SequenceMatcher` similarity vs existing pending+approved texts. Default 0.85, `EXTRACTOR_DEDUPE_RATIO`.
5. **Schema sanity** — `language` is 2-char string, `text` not empty and ≤500 chars.

`is_requirement`/`category`/`certainty` fields used to be gates; all three were removed because small local models flat-line them and they added no signal. The filter strips them defensively if a model still emits them.

## Step 4 — Export pass + Jira push

Trigger: the **Export** tab in the nav becomes active when `recording_state === "idle"` AND ≥1 approved insight exists.

- `POST /export/generate` builds a single prompt from the approved insights (signal) + the full transcript (context). The currently-selected model runs it. The result is `{requirements: [...], decisions: [...]}` stored on `SessionState.export_draft` and broadcast as `ws: export_draft`.
- The UI's **Export view** renders the draft as fully editable cards: issuetype, summary, Given/When/Then, AC list (add/remove rows), six clickable INVEST letters, priority, labels (chip input), story points. Decisions are an editable line list.
- Edits autosave back to the backend after a 500ms debounce via `PUT /export`.
- **Push to Jira** (per card) or **Push all** in the header create issues via `POST /rest/api/3/issue` with ADF descriptions that pin meeting decisions at the top, then User story (G/W/T), Acceptance criteria, INVEST validation. Errors render inline on the card.

## Transcript shaping

Default capture output is **one line per VAD-cut chunk** (the UI shows these as segments). The Step-3 extractor sees the *aggregated* `Utterance`s, not raw segments. The experimental `--paragraphs` flag in `capture/` is a separate, opt-in transcript-rendering mode; speaker- and topic-based grouping are still PRD stretch items.

## Build order

1. **Terminal Live STT** ✅
2. **Beautiful Web UI** ✅
3. **Local LLM Analysis** ✅ — VAD-driven capture, SentenceBuffer, event-driven worker, FOCUS+CONTEXT prompt, gated filter, Approve/Edit/Decline cards. Live model swap (local + cloud), vocabulary hint, recording history.
4. **Requirements & Tickets** ✅ — post-meeting export pass to Jira-ready JSON, fully-editable Export view, per-item + Push-all to Jira REST v3.

## Schemas

Internally we work in seconds (`start_s`, `end_s`). Outbound POST uses milliseconds; convert at the delivery boundary.

**Segment (capture ↔ backend ↔ UI):**
```json
{
  "id": "seg-047",
  "session_id": "sess-20260522-001",
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

**Insight (backend → UI):** category and certainty fields were removed.
```json
{
  "id": "ins-003",
  "session_id": "sess-...",
  "text": "The dashboard must show monthly revenue.",
  "original_text": "...",
  "source_quote": "verbatim span from FOCUS",
  "detail": "one-sentence grounded context from the transcript",
  "language": "en",
  "status": "pending|approved|declined",
  "created_at_iso": "2026-05-22T09:00:00Z"
}
```

**ExportDraft (backend → UI, persisted on SessionState):**
```json
{
  "requirements": [
    {
      "issuetype": "Story|Task|Bug|Epic",
      "summary": "...",
      "description": {
        "user_story": { "given": "...", "when": "...", "then": "..." },
        "acceptance_criteria": ["..."],
        "invest_validation": {
          "independent": true, "negotiable": true, "valuable": true,
          "estimable": true, "small": true, "testable": true
        }
      },
      "priority": "high|medium|low",
      "labels": ["..."],
      "story_points": 3
    }
  ],
  "decisions": [{ "summary": "..." }]
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
{"type": "ai_status",      "state": "ok|no_model|offline|loading|thinking", "model": "phi3", "error": "..."}
{"type": "export_draft",   "draft": { ...ExportDraft... }}
```

## Backend HTTP routes

- `POST /control/start { language? }` · `POST /control/pause` · `POST /control/stop`
- `POST /segments` (from capture)
- `GET /state` · `GET /healthz`
- `GET /history` · `GET /history/{session_id}` · `GET /session/export`
- `GET /insights` · `POST /insights/{id}/approve|decline|edit`
- `GET /ai/status`
- `GET /vocabulary` · `POST /vocabulary { text }` — whisper `--prompt` hint, applied on next ▶ Start
- `GET /model` · `POST /model { model }` — live-swap LLM (local + cloud; gated by API key for cloud)
- `GET /api-keys` · `POST /api-keys { provider, key }` — OpenAI / Anthropic keys, in-memory only
- `GET /export` · `POST /export/generate` · `PUT /export` (replace draft) · `DELETE /export`
- `GET /jira/config` · `POST /jira/config { field, value }` — site URL, email, API token, project key
- `POST /export/push { index }` · `POST /export/push-all`
- `WS /ws` — fan-out

## Non-negotiables

- **Audio never leaves the device.** STT is fully on-device, offline-capable.
- **Local LLM is the default.** Cloud models are opt-in for A/B testing; the user explicitly picks one (with a key) and sees their transcript leave the device. Default stack stays local end-to-end.
- **Mic is the contract.** System/loopback audio is a bonus — never block the demo on it.
- **Diarization is decoration.** If it crashes, the session keeps running.
- **One configurable endpoint.** Staging → prod swap is an env var, not a code change.
- **German is first-class**, not an afterthought. Target: Telekom / Siemens / Volkswagen.
- **Modular processes.** A failure in one component must not cascade. Ollama down → AI panel offline, transcript unaffected.
- **Line-by-line transcript is the default.** The extractor's aggregated `Utterance` is internal — the UI keeps showing raw segment lines.

## Team lanes

- **P01:** UI (React dashboard — pill nav, transcript, insights, history, model + vocabulary controls, Export view + Jira drawer)
- **P02:** Capture + STT (VAD state machine, pywhispercpp, `--api-url` + `--prompt` flags, stable IDs)
- **P03:** Backend + Delivery + LLM extractor (FastAPI, WS broadcast, HTTPS forwarder with retry, subprocess control, SentenceBuffer + ExtractorWorker + LLMRouter + JiraClient)

## Out of scope

- Multi-user views, auth, persistent storage
- Cloud ASR of any kind
- Frontend unit tests (manual acceptance is the contract)
- Real-time diarization (stretch only)

## Open questions

- Exact request schema expected by `staging.doings.de/stt` (we currently send `text/start_ms/end_ms/lang/session_id`)
- Demo hardware (CPU only vs GPU) — determines safe model size
- Is staging endpoint live today? If not, mock with a local FastAPI echo (`uvicorn backend.echo_endpoint:app --port 8001`, then set `DOINGS_ENDPOINT=http://localhost:8001/stt`)
- UI language: DE, EN, or both
