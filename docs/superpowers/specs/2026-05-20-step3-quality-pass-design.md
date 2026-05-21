# Step 3 Quality Pass — Design

**Date:** 2026-05-20
**Status:** Draft for review
**Supersedes:** parts of `2026-05-19-step3-llm-extraction-design.md` (live extraction pipeline)
**Successor work (out of scope here):** Step 4 — post-meeting structuring + Jira push

## Problem

Step 3 ships an extractor that calls a local LLM (Ollama, phi3/mistral) every 5 seconds over a 30s sliding transcript window. Manual acceptance produced cards like these (mistral on a real demo):

- **"product requirements"** — functional, 100% — source: `product requirements`
- **"document for the new"** — functional, 100% — source: `document for the new`
- **"It would be sales made."** — functional, 100% — source: `It would be sales made.`

Three failure modes are visible:

1. **Whisper over-segmentation.** 2s chunks split sentences mid-clause. The LLM sees noun-phrase fragments, not coherent thoughts.
2. **Prompt is too permissive.** Anything containing "requirement" or a future-tense verb passes `is_requirement=true`.
3. **Confidence is meaningless.** Every card is 100%. The 0.6 floor never filters anything.
4. **Duplicates.** The 30s sliding window means each fragment is re-evaluated multiple times. Exact-match dedupe doesn't catch near-duplicates.

## Goal

Make live AI Insights cards trustworthy. The bar: on the demo speech that produced the slop above, the panel shows zero fragment cards, no duplicates, and the certainty label reflects whether the requirement was stated explicitly or inferred.

This is **not** the full Jira-ready extraction. That's Step 4 (see "Future work").

## Non-goals

- Post-meeting structuring into Given/When/Then user stories with INVEST validation (Step 4)
- Export view / JSON download (Step 4)
- Jira API push (Step 4)
- Switching off Ollama / changing the model (orthogonal)
- Anything in `capture/` (whisper segmentation stays as-is)

## Architecture

Three layers of defense, in order from the segment-stream end:

```
capture/ ──> segments ──> SentenceBuffer ──> utterances (queue) ──> ExtractorWorker ──> LLM ──> Filter ──> Insight cards
                          [NEW]                                       [event-driven]            [stricter]
```

### Layer 1 — Input aggregation: `backend/sentence_buffer.py` (new)

Collapses whisper's 2s fragments into coherent utterances before the LLM sees them.

**Behavior:**

- Holds an in-memory list of un-flushed `Segment`s.
- `add(segment)` appends, then checks flush conditions in order:
  1. The buffer's concatenated text ends in `.`, `!`, or `?`.
  2. The gap between the previous segment's `end_s` and this segment's `start_s` exceeds `BUFFER_MAX_SILENCE_S` (default **1.5s**). The triggering segment goes to the **next** buffer, not this one.
  3. The buffer's total duration (`last.end_s - first.start_s`) reaches `BUFFER_MAX_DURATION_S` (default **20.0s**).
- On flush, emits an `Utterance` and clears the buffer.
- On session reset (Stop → Start), the buffer is discarded.

**Utterance shape (frozen dataclass):**

```python
@dataclass(frozen=True)
class Utterance:
    text: str            # segment texts joined with " ", trimmed
    start_s: float       # first segment's start_s
    end_s: float         # last segment's end_s
    lang: str            # most common lang across segments (ties → first)
    segment_ids: list[str]
```

**Delivery:** the buffer publishes to an `asyncio.Queue[Utterance]`. The `ExtractorWorker` is the sole consumer.

**Edge cases:**

- Buffer is empty when a `[BLANK_AUDIO]` or empty-text segment arrives → drop the segment, don't include it.
- Very long single segment (>20s, shouldn't happen with 2s chunks but defensive): emit as a one-segment utterance.
- Session reset while a buffer has pending content: discard, do not emit.

### Layer 2 — Event-driven extraction: `backend/extractor.py` (modified)

Replace the 5s tick with a queue-driven loop.

**Behavior:**

- Worker awaits `queue.get()` on the buffer's queue.
- On each utterance, builds the prompt with:
  - **FOCUS:** the new utterance (the LLM is told to extract **only** from this).
  - **CONTEXT:** the prior 3 utterances, for resolving pronouns/references only. Not for extraction.
- Skip-if-busy: if an LLM call is already in flight, the new utterance is **dropped** (logged). We do not queue up — fresh signals matter more than catching every utterance.
- Existing `EXISTING` block (already-approved requirements) is unchanged, used to tell the LLM what not to re-suggest.

**Retired env vars:** `EXTRACTOR_TICK_S`, `EXTRACTOR_WINDOW_S` (no longer meaningful).

### Layer 3 — Prompt + filter overhaul

#### `backend/extractor_prompt.py` (rewritten)

**Definition (new):**

> A requirement is a **complete clause** containing **either a modal verb** (must / should / shall / will / needs to / has to · muss / soll / wird / braucht) **or a clear intent verb** (need / want / add / show / support / allow / integrate · brauchen / wollen / hinzufügen / zeigen / unterstützen).

**Schema change:** `confidence: float` → `certainty: "explicit" | "implied"`.

- **explicit** — the focus utterance contains a modal or intent verb verbatim.
- **implied** — the requirement is inferred from focus + context, not stated outright.

**Few-shot block:**

BAD examples (with reasoning):
- `"product requirements"` → noun phrase, no verb, not a clause
- `"document for the new"` → fragment, not a clause
- `"how many?"` → question, not a directive
- `"Yeah."` → chatter
- `"It would be sales made."` → ambiguous fragment, no clear requirement

GOOD examples:
- `"The dashboard must show monthly revenue"` → modal verb, complete clause → **explicit**
- `"We need to support German language input"` → intent verb, complete clause → **explicit**
- `"Sales reports should export to CSV"` → modal verb, complete clause → **explicit**
- After context "We're building a CRM" + focus "It needs Salesforce sync" → infer subject is the CRM → **implied**

**Output rule:** the LLM extracts only from FOCUS. CONTEXT is read-only.

#### `backend/extractor_filter.py` (gates in order)

| # | Gate | Default | Env var |
|---|---|---|---|
| 1 | `is_requirement == True` | — | — |
| 2 | `len(text.strip()) >= 40` | 40 | `EXTRACTOR_MIN_TEXT_LEN` |
| 3 | Regex match against EN+DE modal/intent verb list | on | `EXTRACTOR_VERB_GATE` |
| 4 | Source-quote fuzzy match ≥ ratio | 0.75 | `EXTRACTOR_QUOTE_MATCH_RATIO` |
| 5 | Fuzzy dedupe (`SequenceMatcher`) ≥ ratio against pending+approved `text` | 0.85 | `EXTRACTOR_DEDUPE_RATIO` |
| 6 | Schema sanity (certainty in allowed set, category in allowed set, non-empty text) | — | — |

**Retired:** `EXTRACTOR_CONFIDENCE_FLOOR`, `EXTRACTOR_REQUIRE_SOURCE_QUOTE` (source-quote gate is always on; ratio still tunable).

**Verb regex:** compiled once at import. Word-boundary, case-insensitive. EN + DE token lists live as module constants for easy tuning.

#### `backend/insights.py` (schema change)

```python
@dataclass(frozen=True)
class Insight:
    id: str
    session_id: str
    category: Literal["functional", "non_functional"]
    certainty: Literal["explicit", "implied"]   # was: confidence: float
    text: str
    original_text: str
    source_quote: str
    language: str
    status: Literal["pending", "approved", "declined"]
    created_at_iso: str
```

This is a wire-breaking change; no persisted history to migrate.

#### UI — `ui/src/components/InsightCard.tsx` + `ui/src/lib/types.ts`

- Replace the `100%` confidence badge with a certainty badge: cyan "Explicit" / amber "Implied".
- Confidence numbers gone from the UI.

## Env var summary (final)

| Var | Default | Purpose |
|---|---|---|
| `BUFFER_MAX_SILENCE_S` | `1.5` | Gap that flushes the sentence buffer |
| `BUFFER_MAX_DURATION_S` | `20.0` | Hard flush at this duration |
| `EXTRACTOR_MIN_TEXT_LEN` | `40` | Min chars for an extracted requirement |
| `EXTRACTOR_VERB_GATE` | `true` | Require modal/intent verb in `text` |
| `EXTRACTOR_QUOTE_MATCH_RATIO` | `0.75` | Source-quote fuzziness (unchanged) |
| `EXTRACTOR_DEDUPE_RATIO` | `0.85` | Fuzzy dedupe threshold |
| `OLLAMA_MODEL` | `phi3` | Unchanged |
| `OLLAMA_URL` | `http://localhost:11434` | Unchanged |

## Testing strategy

**Unit (new):**
- `backend/tests/test_sentence_buffer.py`
  - Flush on punctuation
  - Flush on silence gap (and split correctness: trigger seg goes to next buffer)
  - Flush on max duration
  - Empty / `[BLANK_AUDIO]` segments dropped
  - Session reset discards pending
  - Language picked correctly (majority, tie → first)

**Unit (modified):**
- `backend/tests/test_extractor_filter.py`
  - Length gate: 39-char text rejected, 40-char accepted
  - Verb gate: text without modal/intent verb rejected (EN + DE cases)
  - Verb gate: bypass when `EXTRACTOR_VERB_GATE=false`
  - Dedupe: 0.86 similarity rejected, 0.84 accepted
  - Certainty schema sanity: invalid value rejected

- `backend/tests/test_extractor.py`
  - Event-driven dispatch on queue put
  - Skip-if-busy drops a second utterance while first is in flight
  - Context window correctly assembled from prior 3 utterances

**Manual acceptance (the bar):**
- Run the same demo speech that produced the screenshot.
- Expectation: zero fragment cards, no duplicates, every card has either "Explicit" or "Implied" badge, every card text is ≥40 chars and contains a modal/intent verb.

## Risk & rollback

**Risks:**

- **Latency increase.** Event-driven means cards now appear when an utterance closes (up to ~20s for a monologue without sentence breaks). Acceptable for hackathon demo; tunable via `BUFFER_MAX_DURATION_S`.
- **Verb gate is too strict for German.** Mitigation: env var bypass; verb list is a module constant, easy to extend.
- **Whisper rarely emits punctuation.** Mitigation: silence gap is the primary trigger; punctuation is a bonus.

**Rollback:** revert the three files (`sentence_buffer.py`, `extractor.py`, `extractor_prompt.py`, `extractor_filter.py`, `insights.py`) + UI badge change. No DB / persisted state to undo.

## Future work (Step 4 — out of scope here)

Captured so we don't lose the thread:

1. **Post-meeting structuring pass.** On Stop, take all approved candidates + the full transcript, run a single richer LLM call producing the Jira-ready schema (user stories with Given/When/Then, acceptance criteria, INVEST validation, action items, decisions, topics). Inputs: approved cards (signal) + full transcript (context). See user's reference schema for the target shape.
2. **Export view.** New UI panel after Stop that shows the structured JSON as reviewable cards (collapsible user stories, AC checklist, INVEST badges). User edits/removes items.
3. **Jira push.** From the Export view, "Push to Jira" creates tickets via the Jira REST API. Needs auth config and ticket-creation error handling.

The live cards (this iteration) become the input curation step for that pipeline.
