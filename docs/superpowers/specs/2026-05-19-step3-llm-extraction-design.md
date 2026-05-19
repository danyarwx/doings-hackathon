# Step 3 — Local LLM Requirements Extraction — Design

**Date:** 2026-05-19
**Scope:** PRD Step 3 (see [voicespec-prd-v3.md](../../../voicespec-prd-v3.md) §9 Step 3) — refocused to "requirements only" extraction (functional / non-functional). Classification of action items, decisions, and chatter is **out of scope** for this step.
**Builds on:** [Step 2 Web UI](2026-05-18-step2-web-ui-design.md)
**Deferred:** Baseline-PRD ingestion + semantic comparison ([Step 3.5](#step-35-stub)).

---

## Goal

While the user is recording, a local LLM reads the rolling 30-second transcript every 5 seconds and proposes software requirements. Each proposed requirement appears in the AI Insights panel as a card with **Approve / Edit / Decline** controls. The user curates the list in real time.

**Done when:**
1. Speaking *"Das System muss mindestens 500 Nutzer unterstützen"* produces a `[functional]` requirement card within ~8s of the utterance ending (typical), ~11s worst case.
2. Clicking **Approve** persists the card as approved for the session.
3. Clicking **Edit** flips the card to an inline textarea; saving updates the text and keeps the card pending.
4. Clicking **Decline** dismisses the card (visually de-emphasized; recorded as declined).
5. If Ollama is offline or the model isn't pulled, the panel header reads "AI offline" and recording still works (segments arrive normally).
6. Restarting the backend with a different `OLLAMA_MODEL` env var (e.g. `phi3` instead of `mistral`) uses the new model with no code changes.

## Non-goals for Step 3

- Action items / decisions / chatter classification (out of the four-class scope in earlier scaffolds; we extract only `requirement`)
- Approve-with-regeneration via LLM (Edit is purely an inline text edit)
- Embedding-based semantic deduplication (Step 3.5 — we use prompt-side dedup here)
- Baseline PRD ingestion / comparison (Step 3.5)
- Cross-session insights persistence (insights are wiped on `idle → recording` like segments are)
- Settings UI for live model swap (env var only)
- Exporting approved requirements as a structured doc / tickets / POST to Doings (Step 4)

---

## Stack

- **LLM runner:** [Ollama](https://ollama.com), local HTTP server at `http://localhost:11434`. Metal-accelerated on Apple Silicon.
- **Default model:** `phi3` (Phi-3-mini, ~2.4GB, ~1.5–3s per call). Chosen for the demo latency budget. Configurable via env var `OLLAMA_MODEL`. Higher-quality alternatives we expect to A/B test: `mistral` (3–5s/call, stronger German), `llama3.1` (5–7s/call, best reasoning), `qwen2.5`.
- **Communication:** Ollama's `POST /api/chat` with `format: "json"` for guaranteed JSON output.
- **Async HTTP:** existing `httpx.AsyncClient` (already in `backend/`).

No new Python dependencies — `httpx` and `pydantic` are already installed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  backend/ (FastAPI, extended)                                        │
│                                                                      │
│  POST /segments ─────────▶ SessionState.add_segment                  │
│                                                                      │
│                  ┌───────────────────────────────────┐               │
│                  │  ExtractorWorker  (asyncio.Task)  │               │
│                  │  - started in lifespan            │               │
│                  │  - tick every 5s                 │               │
│                  │  - runs only when recording_state │               │
│                  │    == "recording"                 │               │
│                  └─────────┬─────────────────────────┘               │
│                            │                                         │
│                            ▼                                         │
│                  ┌───────────────────────────────────┐               │
│                  │  build_window(segments, now,      │               │
│                  │     window_s=30)                  │               │
│                  └─────────┬─────────────────────────┘               │
│                            │                                         │
│                            ▼                                         │
│                  ┌───────────────────────────────────┐               │
│                  │  build_prompt(window,             │               │
│                  │     existing=session.insights)    │               │
│                  └─────────┬─────────────────────────┘               │
│                            │                                         │
│                            ▼                                         │
│                  ┌───────────────────────────────────┐               │
│                  │  ollama_client.chat(messages,     │               │
│                  │     model=OLLAMA_MODEL,           │               │
│                  │     format="json")                │               │
│                  └─────────┬─────────────────────────┘               │
│                            │   JSON {requirements: [...]}            │
│                            ▼                                         │
│                  ┌───────────────────────────────────┐               │
│                  │  validate (pydantic)              │               │
│                  │  dedup vs session.insights        │               │
│                  │  append accepted to               │               │
│                  │    session.insights               │               │
│                  └─────────┬─────────────────────────┘               │
│                            │                                         │
│                            ▼                                         │
│                  WS broadcast: {type:"insight", insight:{...}}       │
│                                                                      │
│  POST /insights/{id}/approve  ─▶ updates status, broadcasts          │
│  POST /insights/{id}/decline                                         │
│  POST /insights/{id}/edit body={text}                                │
│  GET  /insights                                                      │
│  GET  /ai/status                                                     │
└──────────────────────────────────────────────────────────────────────┘
                            │
                            ▼  ws://localhost:8000/ws
                    UI: InsightsPanel renders cards driven by hook
```

### Why a single async worker (not per-segment, not threaded)

- Ollama calls are async-friendly (httpx) and the LLM is single-threaded by nature — one in-flight call at a time avoids thrashing the model.
- Firing on a fixed 5s tick (vs per-segment) prevents redundant calls when whisper emits a burst of segments.
- `asyncio.Task` lives in the FastAPI event loop with everything else — no IPC, no extra process to manage.

### Skip-if-busy semantics

If the previous tick is still running when the next 5s timer fires, **skip this tick**. Don't queue. The LLM can take 1.5–7s depending on model; on slow models / long windows, we'd queue forever. Skipping is acceptable because the *next* tick still sees a complete 30s window.

---

## Components

### `backend/ollama_client.py` — Ollama wrapper

**Purpose:** Pure async client; one function per Ollama endpoint we use.

```python
class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"): ...
    async def chat(self, messages: list[dict], model: str,
                   format: str | None = "json", temperature: float = 0.2,
                   timeout_s: float = 30.0) -> str: ...
    async def health(self, model: str) -> Literal["ok", "no_model", "offline"]: ...
```

`chat` returns the assistant message string. `health` does a `GET /api/tags` and checks `model` is present; returns:
- `"ok"`: Ollama up and model pulled
- `"no_model"`: Ollama up but model name not found
- `"offline"`: connection error / Ollama not running

### `backend/extractor_prompt.py` — Prompt template

Isolated single-file module so prompt iteration is mechanical. Exports `build_messages(window, existing_requirements, locale_hint=None) -> list[dict]`.

The system prompt (verbatim, will be iterated):

```
You are a requirements extractor for engineering meetings. Output ONLY valid JSON
that matches the schema below — no prose, no markdown.

A REQUIREMENT is a statement constraining what the system MUST, SHOULD, or
HAS TO do. Hallmarks:
- Modal verb of obligation (must, shall, should, has to / muss, sollte, soll)
- Refers to system behavior, capability, performance, or a constraint
- Stated as a fact about the product, not as an opinion or aside

EXTRACT
- Functional requirements (what the system does)
- Non-functional requirements (performance, security, reliability,
  scalability, compliance, availability)

DO NOT EXTRACT
- Items already in the EXISTING list (you will receive them — do not repeat)
- Implementation decisions ("we'll use Postgres") unless they encode a
  real constraint
- Questions, opinions, side comments, agreements ("yeah", "ok", "great")
- Generic chatter, meta-talk about the meeting itself
- Things the speaker is hypothesizing or exploring, not committing to

Output the requirement text in the same language as the source quote
(de stays de, en stays en).

For each candidate, INCLUDE an `is_requirement` boolean and a short
`reasoning` (one sentence) — answer those FIRST inside your head before
filling in `text`. If `is_requirement` is false, still include the entry
so the filter can see your reasoning; the backend will drop it.

`source_quote` MUST be the exact words copied from the TRANSCRIPT WINDOW —
no paraphrasing, no shortening. If you can't quote it exactly, set
`is_requirement` to false.

`confidence` must reflect your real confidence (0.0–1.0). Use 0.5 if
unsure. The backend will drop low-confidence items.

SCHEMA
{
  "requirements": [
    {
      "is_requirement": true | false,
      "reasoning": "<one sentence justifying the is_requirement decision>",
      "text": "<the requirement in the source language>",
      "category": "functional" | "non_functional",
      "source_quote": "<exact words from transcript>",
      "language": "de" | "en",
      "confidence": 0.0..1.0
    }
  ]
}

If nothing applies, return {"requirements": []}.
```

User message body:

```
EXISTING (do not duplicate):
- <text 1>
- <text 2>
...

TRANSCRIPT WINDOW (most recent first):
[mm:ss.s][DE] <text>
[mm:ss.s][EN] <text>
...
```

`existing` is the last ~10 non-declined insights. Older ones are dropped to keep the prompt size bounded.

### `backend/extractor.py` — Worker

**Public interface:**

```python
class ExtractorWorker:
    def __init__(self, app: FastAPI, model: str, client: OllamaClient,
                 tick_s: float = 5.0, window_s: float = 30.0): ...
    def start(self) -> None  # creates asyncio.Task, schedules
    async def stop(self) -> None  # cancels + awaits
```

**Behavior:**
- Loop: `await asyncio.sleep(tick_s)` then check `recording_state`.
- If not recording, skip.
- If a previous tick is in-flight (`_in_flight` flag), skip.
- Build window: `[s for s in segments if s.end_s >= max(0, last_segment_end_s - window_s)]`. Use whisper's session-relative times; "now" is the latest segment's end_s.
- Build prompt with last 10 non-declined insights.
- Call `client.chat(...)`.
- Parse JSON; on parse fail or schema fail, log to stderr and continue.
- Run the **quality filter pipeline** (below) over the LLM's candidates.
- For each survivor: create `Insight`, append to `session.insights`, broadcast over WS.
- Errors (Ollama offline, model missing) → broadcast `{type:"ai_status", state:"offline"|"no_model"}`; continue trying next tick.

### Quality filter pipeline

Each candidate from the LLM passes through these gates in order. Failing any gate drops the candidate (logged at debug level for inspection; `reasoning` from the LLM is included in the log line so it's easy to see *why* the model thought something was or wasn't a requirement).

| # | Gate | Drops |
|---|---|---|
| 1 | **`is_requirement` flag** | The LLM's own self-classification. `false` → drop. Cheapest filter; handles the LLM's own "this isn't really a requirement" decision. |
| 2 | **Confidence threshold** | `confidence < EXTRACTOR_CONFIDENCE_FLOOR` → drop. Default `0.6`. Env-var configurable for A/B testing different models — some are calibrated tighter than others. |
| 3 | **Source-quote validation** | The candidate's `source_quote` must appear in the recent transcript window. Implementation: fuzzy substring match (lowercased, punctuation-stripped) using `difflib.SequenceMatcher` against every segment in the window, ratio ≥ 0.75 → pass. Catches hallucinations: if the model invented a quote, it won't match. |
| 4 | **Exact-text dedup** | `text.strip().lower()` already exists among non-declined `session.insights` → drop. Layered fallback under prompt-side dedup. |
| 5 | **Schema sanity** | `category ∈ {"functional", "non_functional"}`, `language ∈ {"de", "en"}` (warn if other), non-empty `text` ≤ 500 chars. Pydantic-enforced. |

All thresholds are env-var configurable so we can re-tune per model during A/B testing:
- `EXTRACTOR_CONFIDENCE_FLOOR` (default `0.6`)
- `EXTRACTOR_QUOTE_MATCH_RATIO` (default `0.75`)
- `EXTRACTOR_REQUIRE_SOURCE_QUOTE` (default `true` — set to `false` to bypass gate 3 if a model produces poor quotes)

The `reasoning` field from the LLM is **not stored on the Insight**; it's used in-process for logging and discarded.

### `backend/insights.py` — Insight model + state

```python
InsightStatus = Literal["pending", "approved", "declined"]

@dataclass(frozen=True)
class Insight:
    id: str            # "ins-NNN"
    session_id: str
    category: Literal["functional", "non_functional"]
    text: str          # current (may be edited)
    original_text: str # what the LLM produced
    source_quote: str
    language: str
    confidence: float
    status: InsightStatus
    created_at_iso: str
```

`SessionState` extended with:
```python
insights: list[Insight] = field(default_factory=list)
```

And `reset()` clears it.

### Backend endpoints

| Method | Path | Effect |
|---|---|---|
| `GET` | `/insights` | All insights of the current session |
| `POST` | `/insights/{id}/approve` | `status=approved`, broadcast `insight_update` |
| `POST` | `/insights/{id}/decline` | `status=declined`, broadcast `insight_update` |
| `POST` | `/insights/{id}/edit` | body `{text: string}`, replaces `text` (keeps status as `pending`), broadcast `insight_update` |
| `GET` | `/ai/status` | `{state: "ok"|"no_model"|"offline", model: "mistral"}` |

All return 404 if the insight id isn't in the current session.

### WS message types added

```json
{"type": "insight",        "insight": { ...Insight... }}
{"type": "insight_update", "id": "...", "status": "...", "text": "..."}
{"type": "ai_status",      "state": "ok|no_model|offline", "model": "mistral"}
```

The frontend hook handles these. `insight_update` is for status/text changes; the full insight identity is unchanged.

### Frontend changes

**`ui/src/lib/types.ts`**
- `InsightStatus = "pending" | "approved" | "declined"` (drop `rejected`)
- `Insight.category: "functional" | "non_functional"` (drop the four-class type union — out of scope)
- `Insight.original_text: string` (new)
- New `AiStatus = "ok" | "no_model" | "offline" | "unknown"`
- `WsMessage` gains `insight | insight_update | ai_status`

**`ui/src/lib/useSessionWs.ts`**
- Track `insights: Map<id, Insight>` and `aiStatus: AiStatus`. Reset on session_id change.
- `insight` message: `next.set(insight.id, insight)`.
- `insight_update` message: patch existing.
- `ai_status` message: update `aiStatus`.

**`ui/src/lib/api.ts`**
- `approveInsight(id)`, `declineInsight(id)`, `editInsight(id, text)`.

**`ui/src/components/InsightCard.tsx`**
- Replace `Reject` with `Decline`.
- Add `Edit` button next to Approve.
- Clicking Edit flips the card to a `textarea` with two buttons: `Save` (calls `editInsight`, returns to view mode, status stays pending) and `Cancel` (discard local change).
- Approved cards show a small "✓ approved" footer in muted style; declined shrink/dim.

**`ui/src/components/InsightsPanel.tsx`**
- Consume insights + aiStatus from the hook (not props).
- Header shows a small status badge: green dot (`ok`), amber (`no_model`), red (`offline`).
- Empty state copy differs by status: `offline` → "Start Ollama and try again"; `no_model` → "Run `ollama pull mistral`"; `ok` and empty → "Speak about requirements to see them appear here."

---

## Data flow per tick

```
t=0s: backend lifespan starts ExtractorWorker
t=5s: tick fires
        recording_state == "recording" ✓
        window = segments where end_s >= last_seg_end - 30
        prompt built
        ollama POST /api/chat (1.5–4s with phi3)
        response = {"requirements": [{"text": "...", ...}, ...]}
        dedup vs session.insights (exact-text)
        for each new: Insight created, appended, WS broadcast
t=10s: tick fires; previous done; new window includes more recent segments
        ...
```

Latency from utterance to card: `whisper chunk (2s) + whisper transcribe (1s) + tick wait (up to 5s) + LLM (1.5-4s with phi3) ≈ 4.5-12s worst case`. Typical: 6-9s. With mistral, add ~2s to both.

---

## Repo layout (delta)

```
backend/
  ollama_client.py      ← NEW
  extractor.py          ← NEW
  extractor_prompt.py   ← NEW
  insights.py           ← NEW (or inlined in state.py)
  server.py             ← extended: new routes, new lifespan tasks
  state.py              ← SessionState gains insights list
  tests/
    test_ollama_client.py   ← NEW (respx mocks)
    test_extractor.py       ← NEW (mocked OllamaClient)
    test_insights.py        ← NEW (endpoint tests)

ui/
  src/
    lib/
      types.ts            ← Insight/AiStatus updates
      useSessionWs.ts     ← new message handlers
      api.ts              ← approve/decline/edit
    components/
      InsightCard.tsx     ← Decline + Edit
      InsightsPanel.tsx   ← reads from hook
```

---

## Testing

### Backend

- `test_ollama_client.py`: respx mocks Ollama `/api/chat`. Test success, JSON return, timeout, connection error.
- `test_extractor.py`: stub `OllamaClient` to return canned JSON. Test:
  - Empty session → no calls to `chat`
  - Window builder picks segments within 30s
  - Quality gate 1: `is_requirement=false` → dropped
  - Quality gate 2: confidence below floor → dropped
  - Quality gate 3: hallucinated source_quote (not in window) → dropped
  - Quality gate 3: paraphrased-but-close source_quote (ratio ≥ 0.75) → kept
  - Quality gate 4: exact-text duplicate of existing insight → dropped
  - Quality gate 5: invalid category or empty text → dropped (pydantic)
  - Malformed JSON output → worker doesn't crash, no insights added
  - Skip-if-busy: simulate slow chat() and verify next tick is skipped
  - `idle` state → tick does nothing
  - Env-var overrides (`EXTRACTOR_CONFIDENCE_FLOOR=0.4` raises pass rate)
- `test_insights.py`: POST a segment, manually invoke worker tick logic, hit approve/decline/edit endpoints, verify WS broadcasts.

### Frontend

Manual acceptance per the "Done when" checklist above. No new unit tests this step (per Step 2 precedent).

### End-to-end manual

1. `ollama serve` running. `ollama pull mistral` done.
2. Start backend + UI + capture as usual.
3. Speak: *"Das System muss mindestens 500 Nutzer unterstützen, und die Authentifizierung muss OAuth 2.0 verwenden."*
4. Within ~15s: two requirement cards appear in the Insights panel, German text, `[functional]` badge.
5. Click Edit on one; change wording; Save. Card returns to view mode with new text, still pending.
6. Click Approve. Footer shows "✓ approved".
7. Click Decline on the other. Card visually dims.
8. Stop recording. Start a new session. Insights panel clears (session_id changed).

---

## Error handling

| Condition | Behavior |
|---|---|
| Ollama not running | Worker catches `httpx.ConnectError`; broadcasts `ai_status: offline`. Tick continues attempting. UI shows red dot + "Start Ollama" copy. |
| Model not pulled | Ollama returns 404. Worker broadcasts `ai_status: no_model`. UI shows amber dot + `ollama pull mistral` copy. |
| Model returns invalid JSON | Logged to stderr; that tick produces zero insights; next tick retries. |
| Model returns valid JSON, wrong schema | Pydantic validation drops invalid items; valid ones pass through. |
| LLM call exceeds tick interval | `_in_flight` flag prevents overlap; next tick is skipped. |
| Recording starts/stops mid-tick | The in-flight tick completes naturally; new insights still broadcast even if state has flipped to `idle` (acceptable — they belong to the just-ended session). |
| Insight id 404 on POST | 404 response; UI logs and ignores. |

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Mistral 7B too slow on demo hardware | Env-var-swappable model — `OLLAMA_MODEL=phi3` halves latency. Document in README. |
| LLM hallucinates requirements not in transcript | `source_quote` is in the schema; UI surfaces it; user decides via Approve/Decline. |
| Duplicates slip through prompt-side dedup | Exact-text dedup is a fallback. Step 3.5 adds embedding dedup. Acceptable for demo. |
| Mixed-language utterances confuse the model | Prompt instructs "same language as source quote". Test in manual acceptance; if shaky, force `--language` on capture. |
| German extraction quality lower than English | Mistral is strong on German; if Phi-3 is poor, document the trade-off. Largest impact on demo audience (Telekom/Siemens/VW) so worth testing. |
| Ollama warmup delay on first call | Worker tolerates a 30s timeout on first call; subsequent calls are fast (model stays loaded). |

---

## What this sets up for Step 3.5 and Step 4

**Step 3.5 (next):**
- Ingest a baseline PRD document (markdown or JSON).
- On each new extracted requirement, compute embedding similarity to the baseline + already-approved set.
- High similarity → "already in PRD" badge or auto-decline.
- Differential view: "this approved requirement is *new* vs the baseline."

**Step 4 (later):**
- Export approved requirements as structured JSON / markdown / ticket payloads per PRD §9 Step 4.
- POST aggregated approved set to `staging.doings.de` (or future Doings ingest endpoint).

---

## Step 3.5 (stub)

Out of scope here. Will spec separately when Step 3 is shipped. The Insight schema already includes `source_quote` and `original_text`, which Step 3.5 needs for semantic comparison.
