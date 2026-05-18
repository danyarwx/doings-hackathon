# Step 1 — Terminal Live STT — Design

**Date:** 2026-05-18
**Scope:** PRD Step 1 only (see [voicespec-prd-v3.md](../../../voicespec-prd-v3.md) §9 Step 1)
**Target platform:** macOS Apple Silicon (M1/M2/M3)

---

## Goal

Speak into the mic. See timestamped, language-tagged transcript lines appear in the terminal within ~3 seconds, fully offline.

**Done when:** A German sentence followed by an English sentence both appear correctly transcribed, each tagged with its detected language and a session-relative timestamp.

## Non-goals for Step 1

No FastAPI, no WebSocket, no Angular UI, no HTTPS delivery, no segment IDs / `session_id`, no JSON output, no diarization, no VAD, no system-audio loopback. Each of those lands in a later PRD step.

---

## Architecture

One Python process, two threads, one bounded queue.

```
┌─────────────────────────────────────────────────────────┐
│  main.py                                                │
│                                                         │
│  ┌──────────────┐   Queue[(start_s, np.ndarray)]        │
│  │ CaptureThread│───────────────────────────────────┐   │
│  │              │                                   ▼   │
│  │ sounddevice  │                          ┌──────────┐ │
│  │ InputStream  │                          │ STT loop │ │
│  │ 16kHz mono   │                          │ (main)   │ │
│  │ float32      │                          │          │ │
│  │              │                          │pywhisper │ │
│  │ Emits 2s     │                          │   cpp    │ │
│  │ windows w/   │                          └────┬─────┘ │
│  │ 200ms overlap│                               │       │
│  └──────────────┘                               ▼       │
│                                         stdout (pretty) │
└─────────────────────────────────────────────────────────┘
```

### Why two threads + a queue

A 2-second chunk takes ~0.5–1.5s to transcribe with `ggml-medium` on M-series. Capture of chunk N+1 must overlap transcription of chunk N or we drop audio. The queue is bounded (maxsize=8) so a stalled transcriber surfaces as backpressure rather than unbounded memory growth.

### Threading model

- **Capture thread** (`capture.py`): owns the `sounddevice.InputStream`. The audio callback appends samples to a ring buffer. Every time the buffer holds ≥ 2.0s of new audio, the thread emits one chunk (`prev_tail_200ms + new_2000ms`, total 35200 samples @ 16kHz) onto the queue along with its session-relative start time in seconds, then retains the trailing 200ms for the next chunk's overlap.
- **Main thread** (`transcribe.py` + `main.py`): blocks on `queue.get()`, calls `model.transcribe(chunk, language=None)`, prints each returned segment via the formatter.
- **Shutdown:** SIGINT sets `stop_event`. Capture thread closes the stream and exits. Main thread drains the queue, then returns.

---

## Components

### `capture/capture.py` — Audio capture

**Purpose:** Produce a stream of fixed-size, 16kHz mono float32 chunks with 200ms overlap.

**Interface:**
```python
def start_capture(out_queue: queue.Queue, stop_event: threading.Event) -> threading.Thread
```

**Behavior:**
- Opens `sounddevice.InputStream(samplerate=16000, channels=1, dtype='float32', blocksize=1600)` (100ms callback cadence).
- Maintains an internal `np.ndarray` buffer. On each callback, appends the block. When `len(buffer) >= 32000` (2s of new audio), splices off the first 32000 samples (the "fresh" portion), prepends the previous chunk's trailing 3200 samples (200ms overlap), pushes `(chunk_start_s, chunk_audio)` to `out_queue`, and keeps the trailing 3200 samples of the *fresh* portion for the next overlap.
- `chunk_start_s` is the session-relative time of the chunk's **first sample** (i.e., of the overlap portion), so whisper's chunk-relative `t=0` maps directly onto it. Concretely: for chunk N (0-indexed), `chunk_start_s = max(0.0, (N * 32000 - 3200) / 16000.0)`. Chunk 0 has no overlap and starts at 0.0.
- Queue is bounded (`maxsize=8`). If full, drop the oldest chunk and log a warning to stderr — we'd rather skip ~2s than block capture.

**Dependencies:** `sounddevice`, `numpy`.

### `capture/transcribe.py` — Whisper wrapper

**Purpose:** Load the model once; transcribe a single chunk on demand.

**Interface:**
```python
class Transcriber:
    def __init__(self, model_name: str = "medium"): ...
    def transcribe(self, audio: np.ndarray, chunk_start_s: float) -> list[Segment]: ...

@dataclass
class Segment:
    text: str
    start_s: float   # session-relative
    end_s: float     # session-relative
    lang: str        # ISO 639-1, e.g. "de", "en"
```

**Behavior:**
- Constructor calls `pywhispercpp.Model("medium", ...)`. Model file lives in `capture/models/`; pywhispercpp will download on first run.
- `transcribe()` calls the underlying model with `language=None` (auto-detect). Returned segments have chunk-relative `t0`/`t1` in centiseconds — we convert to seconds and add `chunk_start_s` to produce session-relative times.
- Whisper's detected language is captured per call (one language per chunk, not per segment — this is a known whisper.cpp constraint; for mixed-language utterances the language tag reflects the dominant language of the 2s window).

**Dependencies:** `pywhispercpp`, `numpy`.

### `capture/formatter.py` — Output formatting

**Purpose:** Convert a `Segment` to the PRD line format.

**Interface:**
```python
def format_segment(seg: Segment) -> str
```

**Output:**
```
[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen.
```

- Timestamps: `MM:SS.t` (one decimal of seconds), session-relative, zero-padded.
- Language tag: uppercased ISO code in brackets.
- Empty-text segments and segments where `text.strip() == ""` are skipped (whisper sometimes emits silence markers).

### `capture/main.py` — Entrypoint

**Purpose:** Wire the pieces, handle signals.

**Behavior:**
1. Parse minimal CLI args: `--model` (default `medium`), `--device` (default system default mic).
2. Construct `Transcriber` (blocks while model loads; print "loading model..." to stderr).
3. Start capture thread.
4. Install SIGINT handler that sets `stop_event`.
5. Loop: `chunk_start_s, audio = queue.get(timeout=0.5)`; on timeout, check stop_event. For each segment from `transcribe()`, print `format_segment(seg)` to stdout, flushed.
6. On stop: print final summary line to stderr (`Stopped. Transcribed N segments in M.M seconds.`).

---

## Repository layout

```
doings/
├── CLAUDE.md
├── voicespec-prd-v3.md
├── capture/                    ← Step 1
│   ├── main.py
│   ├── capture.py
│   ├── transcribe.py
│   ├── formatter.py
│   ├── requirements.txt
│   ├── models/                 ← gitignored
│   ├── tests/
│   │   ├── test_formatter.py
│   │   └── fixtures/           ← short WAV files for offline tests
│   └── README.md
├── backend/                    ← empty placeholder for Step 2
├── ui/                         ← empty placeholder for Step 2
├── docs/superpowers/specs/
│   └── 2026-05-18-step1-terminal-live-stt-design.md  (this file)
└── .gitignore
```

`.gitignore` adds: `capture/models/`, `__pycache__/`, `.venv/`, `*.pyc`.

---

## Dependencies

`capture/requirements.txt`:
```
pywhispercpp>=1.2
sounddevice>=0.4
numpy>=1.24
```

No system-wide whisper.cpp build is required: `pywhispercpp` ships the compiled binary with Metal acceleration on Apple Silicon.

---

## Output contract

Exact format (one segment per line, flushed):

```
[MM:SS.t → MM:SS.t] [XX] <text>
```

Example session:

```
[00:00.4 → 00:03.1] [DE] Das System muss mindestens 500 Nutzer unterstützen.
[00:03.5 → 00:05.8] [EN] Authentication should use OAuth 2.0.
[00:07.1 → 00:09.4] [DE] Ja, and it must also work offline.
```

stderr is used only for diagnostics (model loading, dropped-chunk warnings, final summary). stdout contains only transcript lines — so `python main.py | tee transcript.log` produces a clean log.

---

## Error handling

| Condition | Behavior |
|---|---|
| No input device / mic permission denied | Fail fast at startup with clear message; exit 1. |
| Model file missing and download fails | Fail fast; instruct user to download manually. |
| Queue full (transcriber lagging) | Drop oldest chunk, log to stderr. Don't block capture. |
| `model.transcribe()` raises | Log the chunk's `start_s` and exception to stderr; continue with next chunk. |
| SIGINT | Set stop_event; drain queue; clean shutdown. |

No retry logic, no auto-restart — those come with the FastAPI delivery service in Step 2.

---

## Testing

Step 1 doesn't need extensive automation, but we validate two things:

1. **Unit test** (`tests/test_formatter.py`): `format_segment` produces the exact PRD format for known inputs (DE + EN, edge timestamps).
2. **Manual acceptance**: speak a DE sentence then an EN sentence; verify both appear in the terminal within ~3s with correct language tags and increasing session-relative timestamps. Documented in `capture/README.md`.

A fixture-based transcription test (feeding a pre-recorded WAV through `Transcriber`) is **out of scope** for Step 1 — model output is non-deterministic enough that exact assertions are fragile, and the manual acceptance test catches regressions cheaply.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `ggml-medium` slower than expected on the demo Mac | Model is a CLI arg — fall back to `small` with one flag flip. |
| Whisper hallucinates on silence chunks | Empty-text and whitespace-only segments filtered in formatter. VAD is a Step-2+ improvement. |
| Language detection flaps on short utterances | Accepted limitation for Step 1. Per-chunk language is whisper.cpp's contract; we don't try to override it. |
| pywhispercpp download stalls on first run | README documents manual model download path. |
| Audio callback runs on real-time thread; doing work there causes glitches | Callback only appends to buffer — all chunking work happens in the capture *thread loop*, not the callback. |

---

## What this sets up for Step 2

The `Segment` dataclass is the seed of the PRD's segment schema. Step 2 will:
- Add `id` (`seg-NNN`) and `session_id` fields.
- Replace `print(format_segment(seg))` with `await fanout.publish(seg)` — fan-out to WebSocket and HTTPS POST.
- Reuse `capture.py` and `transcribe.py` unchanged.

The two-thread architecture survives: the FastAPI process becomes a third consumer fed off the same queue (or an in-process async hand-off, decided in Step 2 brainstorming).
