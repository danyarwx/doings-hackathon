# Step 2 — Beautiful Web UI — Design

**Date:** 2026-05-18
**Scope:** PRD Step 2 (see [voicespec-prd-v3.md](../../../voicespec-prd-v3.md) §9 Step 2)
**Builds on:** [Step 1 Terminal Live STT](2026-05-18-step1-terminal-live-stt-design.md)

---

## Goal

Take the working terminal STT pipeline from Step 1 and surface it in a polished web dashboard. Live transcript appears as you speak; each finalized segment is also POSTed to `staging.doings.de/stt`; the UI reflects delivery status per segment.

**Done when:** Starting recording from the UI produces live `[mm:ss.s][lang] text` lines in the transcript panel within ~3 seconds of speaking, the delivery panel shows each segment confirmed (✓/⟳/✗), and pressing Stop ends the session cleanly.

## Non-goals for Step 2

- AI-generated insights / requirement extraction (Step 3 — the insights panel ships as a placeholder)
- Inline transcript editing (PRD has it; defer)
- Speaker chips / diarization (PRD stretch)
- Persistence — session state is in-memory; restarting the backend resets it
- Authentication / multi-user
- Frontend unit tests (manual acceptance is enough at hackathon scope)

---

## Stack (locked)

- **Frontend:** Vite + React 18 + TypeScript + Tailwind CSS
- **Backend:** FastAPI + httpx (async) + WebSocket
- **Capture:** unchanged from Step 1 (pywhispercpp), with one new CLI flag
- **Styling:** Vision-UI inspired dark/glassy aesthetic; no component library

Earlier PRD draft locked Angular; that decision is reversed in [voicespec-prd-v3.md](../../../voicespec-prd-v3.md) §0. Rationale: hackathon prioritizes a fast match to the supplied dark dashboard reference; React + Tailwind hits that aesthetic with less custom theming than Angular + a generic UI kit.

---

## Architecture

Three local processes:

```
┌──────────────────────────────────────────────────────────────────────┐
│                            LOCAL MACHINE                             │
│                                                                      │
│  ┌─────────────────┐   POST /segments    ┌──────────────────────┐    │
│  │  capture        │ ───────────────────►│  FastAPI fan-out     │    │
│  │  (Python)       │   per segment       │  • POST /segments    │    │
│  │                 │                     │  • POST /control/*   │    │
│  │  Spawned by     │◄────────────────────│  • WS /ws            │    │
│  │  backend OR     │   SIGINT on stop    │  • GET /session/...  │    │
│  │  run standalone │                     │  • exp-backoff retry │    │
│  └─────────────────┘                     │    to staging.doings │    │
│                                          └──────┬─────────┬─────┘    │
│                                       ws://     │         │ https    │
│  ┌──────────────────────────────────────────────▼┐        │          │
│  │  React + Vite + TS + Tailwind                 │        │          │
│  │  3-column dashboard                           │        │          │
│  └───────────────────────────────────────────────┘        │          │
└───────────────────────────────────────────────────────────┼──────────┘
                                                            ▼
                                            https://staging.doings.de/stt
                                            (URL configurable via env var)
```

- **One-way control:** UI → Backend → Capture (Start/Stop). Capture never speaks to the UI directly.
- **One-way data:** Capture → Backend → UI (WS) and Backend → staging.doings (HTTPS).

---

## Backend (FastAPI)

**Single file `backend/server.py`** to start. Split if it crosses ~300 lines.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/segments` | Capture posts each finalized segment. Body: `Segment` schema below. |
| `WS` | `/ws` | Bidirectional channel — server pushes `segment`, `delivery`, `state` events. Clients can send `ping` (no other commands in Step 2). |
| `POST` | `/control/start` | Spawn capture subprocess. 200 if started, 409 if already recording. |
| `POST` | `/control/stop` | SIGINT the capture subprocess, wait up to 3s, then SIGKILL. 200 on success, 409 if idle. |
| `GET` | `/state` | Returns `{state, session_id, segment_count, delivered_count}`. Useful for UI reconnect. |
| `GET` | `/session/export` | Returns the current session's segments as JSON. |
| `GET` | `/healthz` | Liveness probe. |

### Schemas

**Inbound `POST /segments` body:**
```json
{
  "id": "seg-047",
  "session_id": "sess-20260518-001",
  "text": "Das System muss mindestens 500 Nutzer unterstützen.",
  "start_s": 12.4,
  "end_s": 15.1,
  "lang": "de"
}
```

**Outbound WS messages** (one JSON per frame):
```json
{"type": "segment", "segment": { ...Segment... }}
{"type": "delivery", "id": "seg-047", "status": "pending|delivered|failed", "attempts": 1}
{"type": "state",    "state": "idle|recording|stopping", "session_id": "..." }
```

**`POST` to `staging.doings.de/stt`:**
```json
{
  "text": "...",
  "start_ms": 12400,
  "end_ms": 15100,
  "lang": "de",
  "session_id": "sess-20260518-001"
}
```
(Note: `start_ms`/`end_ms` are converted from `start_s`/`end_s`. The PRD's POST schema uses milliseconds; our internal schema uses seconds. The conversion happens in the delivery worker.)

### Behavior

- Each incoming segment is:
  1. Stored in `session.segments` (in-memory list).
  2. Broadcast to all WS clients as `{type:"segment", ...}`.
  3. Queued for delivery to `DOINGS_ENDPOINT` via an async worker.
- **Delivery worker** (one per server, processes a `asyncio.Queue`):
  - Sends HTTPS POST with 5s timeout.
  - On 2xx → broadcast `{type:"delivery", status:"delivered"}`.
  - On 5xx or network error → exp backoff (1s, 2s, 4s), max 3 attempts → final status `"failed"`. Intermediate attempts broadcast `{status:"pending", attempts:N}`.
  - On 4xx → mark `failed` immediately; never retry (the request is malformed, retrying won't help).
- **`DOINGS_ENDPOINT`** env var (default `https://staging.doings.de/stt`). For local development a mock echo server can be pointed to (e.g. `http://localhost:8001`).
- **Capture subprocess management:** backend stores `Optional[asyncio.subprocess.Process]`. `start` builds the command line (`python -m capture.main --api-url http://localhost:8000`) and `asyncio.create_subprocess_exec`s it. `stop` sends SIGINT, awaits with 3s timeout, then SIGKILL.

### Session

A session begins on the first incoming segment (or on `POST /control/start`, whichever happens first). `session_id` is `sess-YYYYMMDD-HHMMSS`. Restarting the backend resets the session — that's the trade-off for no persistence.

### Concurrency

FastAPI on `uvicorn` is async. WS broadcast uses a set of connected clients; we send sequentially per client (handle disconnects by removing from the set on send error). The delivery worker is a single coroutine reading from an `asyncio.Queue` — no fan-out parallelism needed at hackathon scale.

---

## Capture process — minimal changes

Two additions to [capture/main.py](../../../capture/main.py):

1. **`--api-url URL`** CLI flag. When set, after each formatted line is printed, `httpx.post(f"{api_url}/segments", json=segment_dict, timeout=1.0)` is called fire-and-forget (caught exceptions logged to stderr, never raised). Stdout output is unchanged.
2. **Stable IDs and session ID.** A `session_id = "sess-" + datetime.now().strftime("%Y%m%d-%H%M%S")` is created at startup. Each emitted segment gets `id = f"seg-{counter:03d}"`. These travel in the POST body.

`segment.py` gets `id: str | None` and `session_id: str | None` fields (optional so existing tests don't break). The formatter ignores them — terminal output stays identical.

No other Step 1 behavior changes.

---

## Frontend (React + Vite + TS + Tailwind)

### File structure

```
ui/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css                    ← Tailwind directives + custom CSS vars
│   ├── components/
│   │   ├── Header.tsx               ← recording dot, timer, counters, Export, Start/Stop
│   │   ├── TranscriptPanel.tsx      ← auto-scrolling segment list
│   │   ├── SegmentCard.tsx          ← one segment row
│   │   ├── DeliveryPanel.tsx        ← delivery status list
│   │   ├── InsightsPanel.tsx        ← Step 3 placeholder
│   │   └── GlassCard.tsx            ← reusable glass-effect card wrapper
│   ├── lib/
│   │   ├── api.ts                   ← fetch helpers for /control/*, /state, /session/export
│   │   ├── useSessionWs.ts          ← WS hook: connects, reconnects, exposes state + segments + deliveries
│   │   └── types.ts                 ← Segment, DeliveryStatus, SessionState types
│   └── styles/
│       └── tokens.css               ← color/gradient/shadow custom properties
└── README.md
```

### Layout

12-column grid, single page, no routing.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Header (col-span 12, h-20)                                           │
│  ● Recording   00:14:32   Segments 47   Delivered 46/47  [▶][■][↓]   │
├──────────────────────┬───────────────────────┬───────────────────────┤
│  TRANSCRIPT (col 6)  │  DELIVERY (col 3)     │  INSIGHTS (col 3)     │
│                      │                       │                       │
│  Scrollable          │  Scrollable           │  Step 3 placeholder   │
│  Auto-scroll bottom  │  Newest on top        │  Static "coming soon" │
│                      │                       │  card                 │
└──────────────────────┴───────────────────────┴───────────────────────┘
```

On viewports < 1024px (lg), columns stack vertically. Mobile is not a target — desktop demo only.

### Components

#### `App.tsx`
Owns session state via `useSessionWs()`. Passes slices to children. Provides handlers for Start, Stop, Export wired to `lib/api.ts`.

#### `Header.tsx`
Props: `state, sessionStart, segmentCount, deliveredCount, onStart, onStop, onExport`.
- Recording dot (red pulsing when `state === "recording"`, gray when idle).
- Timer: `mm:ss` since `sessionStart` (or `00:00` when idle); ticks every second using `setInterval`.
- Counters: `Segments N`, `Delivered N/N`.
- Buttons: `▶ Start` shown when `state === "idle"`, `■ Stop` when `"recording"`, both disabled when `"stopping"`. `↓ Export` always enabled.

#### `TranscriptPanel.tsx`
Props: `segments: Segment[]`.
- Renders newest-at-bottom. Auto-scrolls to bottom when a new segment lands, unless the user has scrolled up (track scrollTop; if user is > 100px from bottom, suspend auto-scroll and show a "Jump to latest" pill at the bottom-right).
- Renders one `SegmentCard` per segment.
- Empty state: centered "Waiting for audio…" with a subtle pulse.

#### `SegmentCard.tsx`
Props: `segment: Segment`.
- Row: `[mm:ss.s]` (muted) · language badge (pill colored by lang) · `text` (white).
- Language badge colors: `EN` cyan, `DE` magenta, other neon blue.
- No hover state in Step 2.

#### `DeliveryPanel.tsx`
Props: `deliveries: Map<string, DeliveryStatus>`.
- Newest segment id at top.
- Each row: monospace `seg-NNN` + status icon (✓ green, ⟳ amber spinning, ✗ red).
- Empty state: "No deliveries yet."

#### `InsightsPanel.tsx`
Static placeholder. Centered icon + text: "AI insights will appear here when Step 3 is wired up." Subtle border-dashed.

#### `GlassCard.tsx`
Wrapper component for the three main panels and the header. Applies:
```
bg-white/5 backdrop-blur-xl border border-white/10
rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.4)]
```

### Hook: `lib/useSessionWs.ts`

```typescript
function useSessionWs(): {
  state: "idle" | "recording" | "stopping" | "disconnected";
  segments: Segment[];
  deliveries: Map<string, DeliveryStatus>;
  sessionId: string | null;
  sessionStart: number | null;
}
```

- Opens `new WebSocket("ws://localhost:8000/ws")` on mount.
- On `segment` messages: appends to `segments`.
- On `delivery` messages: updates `deliveries` map by id.
- On `state` messages: updates `state` and `sessionId`. If state transitions `idle → recording`, sets `sessionStart = Date.now()`. On `recording → idle`, clears `sessionStart`.
- On close/error: reconnects with backoff (1s, 2s, 4s, max 10s).
- While disconnected, `state === "disconnected"` — header shows a small red dot and "Backend offline" tooltip.

### Styling tokens

`src/styles/tokens.css`:
```css
:root {
  --bg-from:        #0B1437;
  --bg-to:          #111c44;
  --neon-cyan:      #01B5E2;
  --neon-blue:      #0075FF;
  --neon-pink:      #FF0080;
  --neon-green:     #2DD4BF;
  --neon-amber:     #FFB547;
  --text-primary:   #FFFFFF;
  --text-muted:     #A0AEC0;
  --glass-bg:       rgba(255, 255, 255, 0.05);
  --glass-border:   rgba(255, 255, 255, 0.10);
}
```

Body has `bg-gradient-to-br from-[var(--bg-from)] to-[var(--bg-to)]`. Inter or system-ui font. No bespoke component library; Tailwind utilities and a handful of custom classes only.

### Acceptance test

1. Start backend: `uvicorn server:app --reload`.
2. Start UI: `npm run dev`.
3. Open `http://localhost:5173`. Header shows `idle`, gray dot.
4. Click `▶ Start`. State transitions to `recording`, dot turns red, timer ticks.
5. Speak: *"Das System muss mindestens 500 Nutzer unterstützen."*
6. Within ~3s: transcript panel shows `[00:0X.X] [DE] …`. Delivery panel shows `seg-001 ⟳` then `✓`.
7. Speak an English sentence; second segment appears tagged `[EN]`.
8. Click `■ Stop`. State returns to `idle`, dot turns gray, timer stops. Capture process exits cleanly (verifiable in backend logs).
9. Click `↓ Export`. Browser downloads `session-<id>.json` with all segments.

---

## Repo layout (after Step 2)

```
doings/
├── CLAUDE.md                       (updated)
├── voicespec-prd-v3.md             (updated: stack v1.2)
├── capture/                        (small CLI flag addition)
├── backend/                        ← NEW
│   ├── server.py
│   ├── requirements.txt
│   ├── tests/
│   │   ├── test_segments.py
│   │   ├── test_control.py
│   │   └── test_delivery.py
│   └── README.md
├── ui/                             ← NEW
│   └── (Vite app)
└── docs/superpowers/
    ├── specs/
    │   ├── 2026-05-18-step1-terminal-live-stt-design.md
    │   └── 2026-05-18-step2-web-ui-design.md      ← this file
    └── plans/
        └── (Step 2 plan will land here)
```

---

## Testing

### Backend (pytest)

- `test_segments.py` — POST a segment, verify it appears in `GET /state` and on the WS broadcast (using `httpx.AsyncClient` and `websockets` test client).
- `test_control.py` — `start` returns 200, second `start` returns 409. `stop` returns 200, second `stop` returns 409. Use a fake "capture" command (`sleep 60`) so tests don't actually launch pywhispercpp.
- `test_delivery.py` — point `DOINGS_ENDPOINT` at a local `respx`/`httpx_mock`. Verify success path emits `delivered`. Verify 500 retries 3 times then emits `failed`. Verify 400 emits `failed` immediately with no retry.

### Frontend

Manual only, per Step 2 acceptance checklist above. Add Vitest later if Step 3 grows the UI complexity.

### Capture

Step 1 tests (26 of them) continue to pass. The new `--api-url` flag is exercised in the Step 2 manual acceptance.

---

## Error handling

| Condition | Behavior |
|---|---|
| Backend down when UI loads | WS reconnects with backoff; header shows "Backend offline" badge. |
| `staging.doings.de/stt` unreachable | Retry 3× then `failed`; subsequent segments keep trying independently. |
| Capture subprocess crashes mid-session | Backend detects via `process.wait()` returning unexpectedly; broadcasts `state:"idle"`; logs to stderr. |
| `POST /segments` from unknown source | Accepted — there's no auth. Acceptable for a local-only hackathon app. |
| WS client sends garbage | Logged; connection closed. |
| Multiple UI tabs open | All receive the same broadcast; all show the same state. No coordination needed. |
| User clicks Start while `stopping` | Button is disabled — UI prevents it. If a stale UI sends it anyway, backend returns 409. |

---

## Risks

| Risk | Mitigation |
|---|---|
| `staging.doings.de/stt` not reachable from dev environment | Env var override; local echo server (`uvicorn echo:app --port 8001`) takes ~10 lines. |
| Capture subprocess hangs on SIGINT | 3s soft kill, then SIGKILL. Capture's signal handling was tested in Step 1 manual runs. |
| WS dropped under load | Auto-reconnect; segments missed during the gap are not replayed in Step 2 (acceptable trade-off; persistence is explicitly out of scope). |
| Tailwind/glass aesthetic doesn't match the reference image | Build with the actual image open; iterate on `tokens.css` until headers/cards visually match before committing component logic. |

---

## What this sets up for Step 3

- The `InsightsPanel` placeholder becomes the LLM extraction card list.
- Backend gains an extraction worker that reads from the same `session.segments` and emits `{type:"insight", ...}` over WS.
- The UI's WS hook gains one more message type; no other plumbing changes.
