# PRD: Local Meeting Intelligence — Doings.ai × CF Hackathon 2026

**Version:** 1.3 (Steps 1–3 shipped; extractor architecture refined)
**Team:** 3 people · 3 lanes · 4 milestones
**Status:** Steps 1, 2, 3 shipped · Step 4 (structured Jira-ready export) next
**Stack:** React 19 + Vite + TypeScript + Tailwind + framer-motion · pywhispercpp (whisper.cpp) · FastAPI · Ollama (phi3 / mistral / llama3.1) · pyannote-audio (stretch)

---

## 0. What changed in v1.3

Building Step 3 surfaced architecture changes worth ratifying:

| Topic | v1.2 | v1.3 |
|---|---|---|
| LLM input window | 30 s rolling segment window, polled every 5 s | **`SentenceBuffer` + event-driven `ExtractorWorker`.** Whisper segments are aggregated into `Utterance`s (flush on silence gap > 1.5 s or 20 s hard cap — punctuation is unreliable). The worker awaits utterances on a queue; no polling. Each call uses a single FOCUS utterance + last 3 CONTEXT utterances for pronoun resolution. |
| Extraction schema | `confidence: float 0–1` | **`certainty: "explicit"\|"implied"`** — small local models flat-line at 100 % confidence, so a binary self-assessment is more honest. UI shows cyan **Explicit** / amber **Implied** badges. |
| Filter | confidence floor + exact-text dedupe | **Six gates in order:** `is_requirement` → length ≥ 40 chars → modal/intent verb regex (EN + DE) → source-quote fuzzy match against FOCUS → fuzzy dedupe ≥ 0.85 against pending+approved → schema sanity. Drops fragments and near-duplicates that previously slipped through. |
| Approve/reject | approve/reject only | **Approve / Edit / Decline** — inline textarea editing of the requirement before approval. |
| UI shell | 3-column layout, no top nav | **Top nav** with History dropdown, Vocabulary editor, live Model picker (phi3 / mistral / llama3.1), Export placeholder. Panels are `max-w-7xl` centered for breathing room. |
| Vocabulary | env-only `--prompt` flag on capture | **UI textarea** posts to `/vocabulary`; whisper picks it up via `--prompt` on the next ▶ Start. |
| Model | env-only `OLLAMA_MODEL` | **Live-swappable** via `/model` route; the `ExtractorWorker` updates its active model without restart. |

## What changed in v1.2

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

- Cloud ASR or cloud LLM of any kind
- Multi-user collaborative view
- Authentication or persistent storage
- (Previously listed: LLM extraction and approve/reject UI — both moved **in scope** as Step 3 and shipped.)

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
**Tech:** React 19 · Vite · TypeScript · Tailwind CSS · framer-motion · lucide-react · ogl (WebGL light rays)
**Style:** Vision-UI-inspired dark/glassy aesthetic (see [docs/superpowers/specs/2026-05-18-step2-web-ui-design.md](docs/superpowers/specs/2026-05-18-step2-web-ui-design.md) for the original Step-2 design)
**Runs:** localhost, browser (Electron shell as stretch)

Responsibilities:
- **Top nav (AppNav)** — `doings` brand · **History** dropdown (past sessions) · **Vocabulary** popover (whisper `--prompt` hint) · **Model** picker (phi3 / mistral / llama3.1, live-swappable) · disabled **Export** button placeholder for Step 4
- **Live Transcript** panel — segments appear over WebSocket; per-segment delivery icons (✓ / ⟳ / ✗)
- **AI Insights** panel — populated by Step 3's `ExtractorWorker`. Each card shows a category + certainty badge and Approve / Edit / Decline controls
- **Control bar** — Start / Pause / Stop with timer; hits `POST /control/*` on the backend
- **Past-session view** — clicking a history item swaps the transcript into a read-only view of that session
- Speaker chips — appear when diarization annotates a segment (stretch, non-blocking)

Layout (top nav + two-column main, panels `max-w-7xl mx-auto`):
```
┌──────────────────────────────────────────────────────────────────────┐
│  ✦ doings  local                  History · Vocabulary · phi3 ▾ │ Export soon │
├──────────────────────┬───────────────────────────────────────────────┤
│  LIVE TRANSCRIPT     │  AI INSIGHTS                       AI ●ok    │
│                      │                                              │
│  [00:12.4] [DE]      │  ┌── FUNCTIONAL · EXPLICIT ─────────────────┐ │
│  Das System muss...  │  │ The dashboard must show monthly revenue.│ │
│                      │  │ "…must show monthly revenue…"           │ │
│  [00:17.0] [EN]      │  │ [✓ Approve] [✎ Edit] [✗ Decline]         │ │
│  Auth should use     │  └─────────────────────────────────────────┘ │
│  OAuth 2.0           │                                              │
├──────────────────────┴───────────────────────────────────────────────┤
│   ● Recording  00:14:32   [▶ Start]  [⏸ Pause]  [■ Stop]           │
└──────────────────────────────────────────────────────────────────────┘
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
- Top AppNav (History dropdown, Vocabulary editor, live Model picker, Export placeholder)
- Live transcript view (WebSocket consumer) + delivery icons inline
- AI insights panel (category + certainty badges, Approve / Edit / Decline)
- Session controls: Start / Pause / Stop + timer — hits `POST /control/*` on the backend
- Past-session viewer (read-only history playback)
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

### Step 3 — Local LLM Analysis ✅ shipped
*"The transcript is now understood, not just captured."*

A local language model reads coherent **utterances** (not raw whisper fragments) and surfaces
requirement candidates. The user approves / edits / declines each card inline during the meeting.

**Architecture (as shipped):**

1. **`SentenceBuffer`** aggregates whisper's ~2 s segments into `Utterance`s. Flush triggers:
   silence gap > 1.5 s (`BUFFER_MAX_SILENCE_S`) or 20 s hard cap (`BUFFER_MAX_DURATION_S`).
   Terminal punctuation is **not** a flush trigger — whisper emits `.` at every chunk boundary,
   so it's noise, not a real sentence signal. Blank-audio segments are dropped.
2. **`ExtractorWorker`** is event-driven (no polling). It awaits utterances on an `asyncio.Queue`.
   For each utterance it builds a prompt with one FOCUS utterance and up to 3 CONTEXT utterances
   (read-only, for pronoun resolution). Skip-if-busy: if an LLM call is already in flight,
   the new utterance is dropped — fresh signals matter more than catching every one.
3. **Filter gates** (in order, each drops with a logged reason):
   1. `is_requirement == True`
   2. `len(text) >= EXTRACTOR_MIN_TEXT_LEN` (default 40)
   3. Regex match against EN+DE modal/intent verb list (`EXTRACTOR_VERB_GATE`)
   4. `source_quote` fuzzy-matches the FOCUS utterance (≥ `EXTRACTOR_QUOTE_MATCH_RATIO`, default 0.75)
   5. Fuzzy dedupe against existing pending+approved (≥ `EXTRACTOR_DEDUPE_RATIO`, default 0.85)
   6. Schema sanity (`certainty` ∈ {explicit, implied}, `category` ∈ {functional, non_functional})
4. **UI**: Approve / Edit / Decline per card. Each shows a category badge and a certainty badge
   (cyan **Explicit** = modal/intent verb present verbatim; amber **Implied** = inferred from
   context). The top nav lets the user live-swap the Ollama model and edit the meeting
   vocabulary that whisper uses as a `--prompt` hint.

**Done when** (✅): Speaking a requirement in German or English produces a structured card
in the UI within ~5–12 s, gated against fragments and duplicates, which the user can
approve / edit / decline with one click.

**Extraction output schema (LLM → backend):**
```json
{
  "is_requirement": true | false,
  "reasoning": "<one sentence>",
  "text": "<requirement in source language, complete clause, ≥40 chars>",
  "category": "functional" | "non_functional",
  "source_quote": "<exact words from FOCUS utterance>",
  "language": "de" | "en",
  "certainty": "explicit" | "implied"
}
```

**Insight schema (backend → UI):**
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
  "status": "pending" | "approved" | "declined",
  "created_at_iso": "2026-05-20T09:00:00Z"
}
```

**LLM setup:**
```bash
ollama pull phi3           # ~2.4 GB, default — fast on a laptop
ollama pull mistral        # ~4 GB, stronger German + instruction following
ollama pull llama3.1       # ~5 GB, best reasoning
ollama serve               # exposes REST API at localhost:11434
```

**Tech:** Ollama · phi3 / mistral / llama3.1 · FastAPI LLM proxy + SentenceBuffer + event-driven ExtractorWorker · React card components

---

### Step 4 — Requirements & Tickets ✦ Next
*"Approved items become engineering artifacts."*

A hybrid pipeline: the live Step-3 cards are the **curation step**. On Stop, a richer LLM pass
takes the approved cards + the full transcript and produces a Jira-ready structured document.
The user reviews it in an **Export** view and pushes selected items to Jira.

**What it does:**
- All approved cards from Step 3 are passed as "signal" to a second LLM call alongside the
  full transcript as "context"
- The LLM expands each into a user story with Given / When / Then, acceptance criteria, and
  INVEST validation; it also extracts action items, decisions, and topics from the transcript
- Output is a structured document conforming to Doings.ai's internal schema (see below)
- A new **Export** view in the UI shows the structured JSON as reviewable, collapsible cards;
  the user can edit / remove items before pushing
- "Push to Jira" creates tickets via the Jira REST API (or POSTs to Doings ingest endpoint)

**Done when:** At the end of a simulated meeting, clicking "Generate Requirements" produces
a clean list of numbered requirements and draft tickets, correctly in German or English,
that Doings.ai's team can recognise as valid input to their pipeline.

**Done when:** At the end of a simulated meeting, clicking "Generate Requirements" produces a
clean Jira-ready document (user stories with Given/When/Then, acceptance criteria, INVEST
validation, action items, decisions, topics), correctly in German or English, that the user
can review and push to Jira.

**Deliverables:**
- [ ] Post-meeting LLM pass: input = approved cards + full transcript; output = Jira-ready JSON
- [ ] Export view in the UI — collapsible user stories, AC checklist, INVEST badges, edit/remove
- [ ] Jira REST API integration (or Doings ingest POST) with auth config + error handling
- [ ] Stretch: download as JSON / markdown
- [ ] Pre-recorded DE/EN fallback demo clip covering all four steps
- [ ] Full live demo rehearsed at least twice

**Output schema (Jira-ready, abbreviated — see [docs/superpowers/specs/2026-05-20-step3-quality-pass-design.md](docs/superpowers/specs/2026-05-20-step3-quality-pass-design.md) "Future work" for the brainstormed full schema):**
```json
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
      "labels": ["frontend", "backend", "auth"],
      "story_points": null
    }
  ],
  "action_items": [{ "task": "...", "owner": null, "deadline": null, "priority": "medium" }],
  "decisions":    [{ "summary": "what was decided" }],
  "topics":       ["topic 1", "topic 2"]
}
```

**Tech:** Ollama (richer pass, larger context) · FastAPI export endpoint · React Export view · Jira REST API / Doings ingest

---

### Roadmap summary

| Step | Name | Output | Demoable alone |
|---|---|---|---|
| 1 | Terminal Live STT ✅ shipped | Text in terminal | ✅ Yes |
| 2 | Beautiful Web UI ✅ shipped | Live transcript in browser + delivery + history | ✅ Yes |
| 3 | Local LLM Analysis ✅ shipped | Approve/edit/decline cards live, with live model swap and vocabulary hints | ✅ Yes |
| 4 | Requirements & Tickets 🔲 next | Structured Jira-ready spec + tickets → Doings pipeline | ✅ Yes |

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

See [README.md](README.md) for the full setup. The short version:

```bash
# Python venvs (3.10+)
/opt/homebrew/bin/python3.14 -m venv capture/.venv
capture/.venv/bin/pip install -r capture/requirements.txt
/opt/homebrew/bin/python3.14 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# UI
cd ui && npm install && cd ..

# Ollama (Step 3+)
brew install ollama && ollama serve
ollama pull phi3

# Four terminals
ollama serve                                                                 # T0
PYTHONPATH=. backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001 # T1
OLLAMA_MODEL=phi3 DOINGS_ENDPOINT=http://localhost:8001/stt \
  PYTHONPATH=. backend/.venv/bin/uvicorn backend.server:app --reload --port 8000  # T2
cd ui && npm run dev                                                         # T3
```

The whisper model (`ggml-medium`, ~769 MB) downloads automatically on first capture run.

---

## 12. Open questions

- Can Doings share the expected request schema for `staging.doings.de/stt`? *(Confirm field names before Step 4)*
- What hardware does the demo laptop have — CPU only or GPU? *(Determines safe whisper + Ollama model size)*
- Is the staging endpoint live and accepting test POSTs today? *(Mock it locally if not — `backend/echo_endpoint.py` is the stand-in.)*
- Should the React UI be in German, English, or both?
- Step 4 target: push directly to Jira via REST API, or route through a Doings ingest endpoint?
