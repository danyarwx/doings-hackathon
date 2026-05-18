# Step 1 — Terminal Live STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speak into the mic, see timestamped language-tagged transcript lines in the terminal within ~3s, fully offline on macOS Apple Silicon.

**Architecture:** Single Python process. Capture thread pushes 2s+200ms-overlap chunks of 16kHz mono float32 audio into a bounded queue. Main thread runs `pywhispercpp` on each chunk and prints formatted segments to stdout.

**Tech Stack:** Python 3.11+, `pywhispercpp` (bundles whisper.cpp with Metal accel), `sounddevice`, `numpy`, `pytest`.

**Spec:** [docs/superpowers/specs/2026-05-18-step1-terminal-live-stt-design.md](../specs/2026-05-18-step1-terminal-live-stt-design.md)

---

## File Structure

Files this plan creates:

| File | Responsibility |
|---|---|
| `capture/requirements.txt` | Pinned Python deps |
| `capture/segment.py` | `Segment` dataclass — shared type |
| `capture/formatter.py` | `format_segment(seg) -> str` — PRD line format |
| `capture/capture.py` | `start_capture(queue, stop_event)` — mic → chunks |
| `capture/transcribe.py` | `Transcriber.transcribe(audio, chunk_start_s) -> list[Segment]` |
| `capture/main.py` | CLI entrypoint; wires capture + transcribe + formatter |
| `capture/tests/test_formatter.py` | Unit tests for formatter |
| `capture/tests/test_segment_timing.py` | Unit tests for chunk-relative → session-relative conversion (pure function, no audio needed) |
| `capture/README.md` | Run instructions + manual acceptance test |
| `.gitignore` | Ignore models, venv, pycache |

Decomposition rationale: each file has a single, testable responsibility. `segment.py` exists so `formatter.py` and its tests don't import the whisper module (keeps tests fast and dependency-free).

---

### Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`
- Create: `capture/requirements.txt`
- Create: `capture/README.md`
- Create: `capture/tests/__init__.py` (empty)
- Create: `capture/__init__.py` (empty)

- [ ] **Step 1: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# Models (downloaded on first run, large)
capture/models/

# OS
.DS_Store

# IDE
.vscode/
.idea/
```

- [ ] **Step 2: Create `capture/requirements.txt`**

```
pywhispercpp>=1.2.0
sounddevice>=0.4.6
numpy>=1.24.0
pytest>=7.4.0
```

- [ ] **Step 3: Create empty package markers**

```bash
touch capture/__init__.py capture/tests/__init__.py
mkdir -p capture/models capture/tests/fixtures
```

- [ ] **Step 4: Create `capture/README.md`**

```markdown
# capture — Step 1: Terminal Live STT

Mic → whisper.cpp → timestamped lines in the terminal. Fully offline.

## Setup (macOS Apple Silicon)

```bash
cd capture
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

First run downloads the `ggml-medium` model (~769MB) into `capture/models/`.

## Run

```bash
python -m capture.main
```

Speak. Lines appear like:

```
[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen.
[00:17.0 → 00:19.3] [EN] Authentication should use OAuth 2.0.
```

Press Ctrl-C to stop.

## Options

```bash
python -m capture.main --model small      # smaller, faster, less accurate
python -m capture.main --model medium     # default
python -m capture.main --device 2         # pick a specific input device
python -m capture.main --list-devices     # print available input devices
```

## Manual acceptance test

1. Run `python -m capture.main`.
2. Wait for `model loaded.` on stderr.
3. Speak: "Das System muss mindestens 500 Nutzer unterstützen."
4. Within ~3s, a line should appear tagged `[DE]` with the German text.
5. Speak: "Authentication should use OAuth 2.0."
6. Within ~3s, a line should appear tagged `[EN]` with the English text.
7. Press Ctrl-C. Final summary line on stderr.

## Tests

```bash
pytest capture/tests
```
```

- [ ] **Step 5: Verify Python is available and install deps**

Run: `cd /Users/danila/Documents/doings && python3 -m venv capture/.venv && source capture/.venv/bin/activate && pip install -r capture/requirements.txt`
Expected: dependencies install cleanly. `pywhispercpp` may compile briefly.

- [ ] **Step 6: Commit**

```bash
git add .gitignore capture/
git commit -m "scaffold capture/ with deps and README"
```

---

### Task 2: `Segment` dataclass

**Files:**
- Create: `capture/segment.py`
- Test: (no test — pure dataclass; exercised via formatter tests in Task 3)

- [ ] **Step 1: Create `capture/segment.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """A transcribed segment with session-relative timing."""

    text: str
    start_s: float
    end_s: float
    lang: str
```

- [ ] **Step 2: Commit**

```bash
git add capture/segment.py
git commit -m "add Segment dataclass"
```

---

### Task 3: Formatter (TDD)

**Files:**
- Create: `capture/formatter.py`
- Test: `capture/tests/test_formatter.py`

- [ ] **Step 1: Write failing tests**

Create `capture/tests/test_formatter.py`:

```python
from capture.formatter import format_segment
from capture.segment import Segment


def test_german_segment():
    seg = Segment(
        text="Das System muss mindestens 500 Nutzer unterstützen.",
        start_s=12.4,
        end_s=15.1,
        lang="de",
    )
    assert format_segment(seg) == (
        "[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen."
    )


def test_english_segment():
    seg = Segment(text="Authentication should use OAuth 2.0.", start_s=17.0, end_s=19.3, lang="en")
    assert format_segment(seg) == "[00:17.0 → 00:19.3] [EN] Authentication should use OAuth 2.0."


def test_zero_padding():
    seg = Segment(text="hi", start_s=0.4, end_s=3.1, lang="en")
    assert format_segment(seg) == "[00:00.4 → 00:03.1] [EN] hi"


def test_minutes_past_one_hour():
    # Session-relative time keeps growing; we don't wrap at 60 minutes.
    seg = Segment(text="long meeting", start_s=3661.5, end_s=3663.0, lang="en")
    assert format_segment(seg) == "[61:01.5 → 61:03.0] [EN] long meeting"


def test_empty_text_returns_none():
    seg = Segment(text="", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) is None


def test_whitespace_only_text_returns_none():
    seg = Segment(text="   ", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) is None


def test_strips_text():
    seg = Segment(text="  hello  ", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) == "[00:01.0 → 00:02.0] [EN] hello"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/danila/Documents/doings && source capture/.venv/bin/activate && pytest capture/tests/test_formatter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capture.formatter'`

- [ ] **Step 3: Implement `capture/formatter.py`**

```python
from capture.segment import Segment


def _fmt_ts(seconds: float) -> str:
    """Format seconds as MM:SS.t (one decimal). Minutes can exceed 59."""
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes:02d}:{remaining:04.1f}"


def format_segment(seg: Segment) -> str | None:
    """Return the PRD line format, or None if the segment text is empty/whitespace."""
    text = seg.text.strip()
    if not text:
        return None
    return f"[{_fmt_ts(seg.start_s)} → {_fmt_ts(seg.end_s)}] [{seg.lang.upper()}] {text}"
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest capture/tests/test_formatter.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add capture/formatter.py capture/tests/test_formatter.py
git commit -m "add formatter for transcript lines"
```

---

### Task 4: Chunk timing helper (TDD)

The chunk timing math is the most subtle part of the design. Pulling it into a pure function lets us test it without audio hardware.

**Files:**
- Modify: `capture/capture.py` (create the file with one helper)
- Test: `capture/tests/test_segment_timing.py`

- [ ] **Step 1: Write failing tests**

Create `capture/tests/test_segment_timing.py`:

```python
from capture.capture import chunk_start_seconds


def test_first_chunk_starts_at_zero():
    # Chunk 0: no overlap available, starts at t=0
    assert chunk_start_seconds(chunk_index=0, fresh_samples=32000, overlap_samples=3200) == 0.0


def test_second_chunk_includes_overlap():
    # Chunk 1: 32000 fresh samples have been emitted, the chunk's first sample
    # is the 200ms-overlap sample → starts at (32000 - 3200) / 16000 = 1.8s
    assert chunk_start_seconds(chunk_index=1, fresh_samples=32000, overlap_samples=3200) == 1.8


def test_third_chunk():
    # Chunk 2: 64000 fresh samples emitted, chunk starts at (64000 - 3200) / 16000 = 3.8s
    assert chunk_start_seconds(chunk_index=2, fresh_samples=32000, overlap_samples=3200) == 3.8


def test_chunk_index_grows():
    # Chunk 10: 320000 fresh samples emitted → (320000 - 3200) / 16000 = 19.8s
    assert chunk_start_seconds(chunk_index=10, fresh_samples=32000, overlap_samples=3200) == 19.8
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest capture/tests/test_segment_timing.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Create `capture/capture.py` with the helper**

```python
"""Microphone capture: emits fixed-size chunks with overlap into a queue."""

from __future__ import annotations

SAMPLE_RATE = 16000
CHUNK_SECONDS = 2.0
OVERLAP_SECONDS = 0.2

FRESH_SAMPLES = int(SAMPLE_RATE * CHUNK_SECONDS)      # 32000
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_SECONDS)  # 3200


def chunk_start_seconds(chunk_index: int, fresh_samples: int, overlap_samples: int) -> float:
    """Session-relative time of a chunk's first sample (including overlap).

    Chunk 0 has no preceding overlap, so it starts at 0.0.
    Chunk N (N>=1) starts overlap_samples before the end of the (N-1)th fresh block.
    """
    if chunk_index == 0:
        return 0.0
    return (chunk_index * fresh_samples - overlap_samples) / SAMPLE_RATE
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest capture/tests/test_segment_timing.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add capture/capture.py capture/tests/test_segment_timing.py
git commit -m "add chunk timing helper"
```

---

### Task 5: Capture thread

**Files:**
- Modify: `capture/capture.py`

This task is **not TDD** — exercising a live audio stream in unit tests is fragile and slow. The timing math from Task 4 is the testable core; the thread loop is integration-tested by manual acceptance in Task 7.

- [ ] **Step 1: Extend `capture/capture.py` with the thread**

Replace the contents of `capture/capture.py` with:

```python
"""Microphone capture: emits fixed-size chunks with overlap into a queue."""

from __future__ import annotations

import queue
import sys
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_SECONDS = 2.0
OVERLAP_SECONDS = 0.2
CALLBACK_BLOCKSIZE = 1600  # 100ms

FRESH_SAMPLES = int(SAMPLE_RATE * CHUNK_SECONDS)      # 32000
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_SECONDS)  # 3200


def chunk_start_seconds(chunk_index: int, fresh_samples: int, overlap_samples: int) -> float:
    """Session-relative time of a chunk's first sample (including overlap).

    Chunk 0 has no preceding overlap, so it starts at 0.0.
    Chunk N (N>=1) starts overlap_samples before the end of the (N-1)th fresh block.
    """
    if chunk_index == 0:
        return 0.0
    return (chunk_index * fresh_samples - overlap_samples) / SAMPLE_RATE


def start_capture(
    out_queue: "queue.Queue[tuple[float, np.ndarray]]",
    stop_event: threading.Event,
    device: int | None = None,
) -> threading.Thread:
    """Start a background thread that captures mic audio and pushes chunks to out_queue.

    Each queue item is (chunk_start_s, audio_float32). The audio array has
    FRESH_SAMPLES + OVERLAP_SAMPLES samples (35200 @ 16kHz = 2.2s), where the
    leading OVERLAP_SAMPLES come from the tail of the previous chunk. Chunk 0
    has no leading overlap and contains FRESH_SAMPLES samples only.

    If the queue is full, the oldest item is dropped and a warning is written
    to stderr — capture must never block.
    """

    def run() -> None:
        buffer = np.zeros(0, dtype=np.float32)
        prev_tail = np.zeros(0, dtype=np.float32)
        chunk_index = 0
        sd_queue: "queue.Queue[np.ndarray]" = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[capture] {status}", file=sys.stderr)
            sd_queue.put(indata[:, 0].copy())

        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CALLBACK_BLOCKSIZE,
                device=device,
                callback=callback,
            )
        except sd.PortAudioError as exc:
            print(f"[capture] failed to open input stream: {exc}", file=sys.stderr)
            stop_event.set()
            return

        with stream:
            while not stop_event.is_set():
                try:
                    block = sd_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                buffer = np.concatenate((buffer, block))

                while len(buffer) >= FRESH_SAMPLES:
                    fresh = buffer[:FRESH_SAMPLES]
                    buffer = buffer[FRESH_SAMPLES:]
                    chunk = np.concatenate((prev_tail, fresh))
                    start_s = chunk_start_seconds(chunk_index, FRESH_SAMPLES, OVERLAP_SAMPLES)
                    try:
                        out_queue.put_nowait((start_s, chunk))
                    except queue.Full:
                        try:
                            out_queue.get_nowait()
                            out_queue.put_nowait((start_s, chunk))
                            print(
                                "[capture] queue full — dropped oldest chunk",
                                file=sys.stderr,
                            )
                        except queue.Empty:
                            pass
                    prev_tail = fresh[-OVERLAP_SAMPLES:].copy()
                    chunk_index += 1

    thread = threading.Thread(target=run, name="capture", daemon=True)
    thread.start()
    return thread


def list_input_devices() -> list[tuple[int, str]]:
    """Return [(index, name)] for all input-capable devices."""
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]
```

- [ ] **Step 2: Verify timing tests still pass**

Run: `pytest capture/tests/test_segment_timing.py -v`
Expected: 4 passed.

- [ ] **Step 3: Smoke-test the import**

Run: `python -c "from capture.capture import start_capture, list_input_devices; print(list_input_devices())"`
Expected: a non-empty list of input devices is printed.

- [ ] **Step 4: Commit**

```bash
git add capture/capture.py
git commit -m "add mic capture thread with chunking and overlap"
```

---

### Task 6: Transcriber

**Files:**
- Create: `capture/transcribe.py`

This task is also **not TDD**: pywhispercpp's output is non-deterministic in detail (timestamps shift, hallucinations vary), so unit-asserting on it is fragile. Manual acceptance in Task 7 validates real behavior.

- [ ] **Step 1: Create `capture/transcribe.py`**

```python
"""Whisper.cpp wrapper. Loads the model once; transcribes one chunk per call."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pywhispercpp.model import Model

from capture.segment import Segment

MODELS_DIR = Path(__file__).parent / "models"


class Transcriber:
    def __init__(self, model_name: str = "medium") -> None:
        print(f"[transcribe] loading model '{model_name}'...", file=sys.stderr)
        MODELS_DIR.mkdir(exist_ok=True)
        self._model = Model(
            model=model_name,
            models_dir=str(MODELS_DIR),
            print_realtime=False,
            print_progress=False,
            print_timestamps=False,
        )
        print("[transcribe] model loaded.", file=sys.stderr)

    def transcribe(self, audio: np.ndarray, chunk_start_s: float) -> list[Segment]:
        """Transcribe one chunk and return session-relative segments."""
        raw_segments = self._model.transcribe(audio, language="auto")
        lang = getattr(self._model, "lang_detected", None) or "??"
        out: list[Segment] = []
        for s in raw_segments:
            # pywhispercpp returns t0/t1 in centiseconds.
            start_s = chunk_start_s + s.t0 / 100.0
            end_s = chunk_start_s + s.t1 / 100.0
            out.append(Segment(text=s.text, start_s=start_s, end_s=end_s, lang=lang))
        return out
```

- [ ] **Step 2: Smoke-test the import (model not loaded yet)**

Run: `python -c "from capture.transcribe import Transcriber; print('import ok')"`
Expected: `import ok` printed. (Constructing `Transcriber()` triggers a model download on first run — skip until Task 7.)

- [ ] **Step 3: Commit**

```bash
git add capture/transcribe.py
git commit -m "add Transcriber wrapping pywhispercpp"
```

---

### Task 7: CLI entrypoint + first end-to-end run

**Files:**
- Create: `capture/main.py`

- [ ] **Step 1: Create `capture/main.py`**

```python
"""Step 1 entrypoint: mic → whisper.cpp → terminal."""

from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
import time

from capture.capture import list_input_devices, start_capture
from capture.formatter import format_segment
from capture.transcribe import Transcriber


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local live STT to the terminal.")
    p.add_argument("--model", default="medium", help="Whisper model (default: medium)")
    p.add_argument("--device", type=int, default=None, help="Input device index")
    p.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_devices:
        for idx, name in list_input_devices():
            print(f"{idx}: {name}")
        return 0

    transcriber = Transcriber(model_name=args.model)

    chunk_queue: "queue.Queue[tuple[float, object]]" = queue.Queue(maxsize=8)
    stop_event = threading.Event()

    def handle_sigint(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    capture_thread = start_capture(chunk_queue, stop_event, device=args.device)
    print("[main] recording. press Ctrl-C to stop.", file=sys.stderr)

    segment_count = 0
    started_at = time.monotonic()

    try:
        while not stop_event.is_set():
            try:
                chunk_start_s, audio = chunk_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                segs = transcriber.transcribe(audio, chunk_start_s)
            except Exception as exc:
                print(
                    f"[main] transcribe failed at t={chunk_start_s:.1f}s: {exc}",
                    file=sys.stderr,
                )
                continue
            for seg in segs:
                line = format_segment(seg)
                if line:
                    print(line, flush=True)
                    segment_count += 1
    finally:
        stop_event.set()
        capture_thread.join(timeout=2.0)
        elapsed = time.monotonic() - started_at
        print(
            f"[main] stopped. transcribed {segment_count} segments in {elapsed:.1f}s.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: List input devices to confirm the mic is visible**

Run: `python -m capture.main --list-devices`
Expected: a numbered list including the built-in mic (e.g. `0: MacBook Pro Microphone`).

- [ ] **Step 3: Run the live STT (this triggers model download on first run, ~769MB)**

Run: `python -m capture.main`
Expected (on stderr):
```
[transcribe] loading model 'medium'...
[transcribe] model loaded.
[main] recording. press Ctrl-C to stop.
```

- [ ] **Step 4: Manual acceptance test**

Following `capture/README.md`:
1. Speak: "Das System muss mindestens 500 Nutzer unterstützen."
2. Within ~3s, expect a line like `[00:0X.X → 00:0Y.Y] [DE] Das System muss mindestens 500 Nutzer unterstützen.` on stdout.
3. Speak: "Authentication should use OAuth 2.0."
4. Within ~3s, expect a line tagged `[EN]` with the English text.
5. Press Ctrl-C; expect the final summary on stderr.

If German is mangled, re-run with `--model large-v3`. If both languages fail, check the input device with `--list-devices` and pass `--device N`.

- [ ] **Step 5: Run unit tests once more**

Run: `pytest capture/tests -v`
Expected: all tests pass (formatter + timing).

- [ ] **Step 6: Commit**

```bash
git add capture/main.py
git commit -m "add CLI entrypoint and wire end-to-end pipeline"
```

---

### Task 8: Finalize

**Files:**
- Modify: `capture/README.md` (only if Task 7 surfaced an inaccuracy)

- [ ] **Step 1: If anything in the README was wrong (e.g. exact device-listing output, model name), correct it.** No commit needed if nothing changed.

- [ ] **Step 2: Final status check**

Run: `git status && git log --oneline -10`
Expected: clean working tree; commits visible for scaffold, segment, formatter, timing, capture, transcribe, main.

---

## Self-Review Notes

**Spec coverage check:**
- Architecture (two threads + queue): Tasks 5, 7 ✓
- `Segment` dataclass: Task 2 ✓
- Capture (2s + 200ms overlap, bounded queue, drop-oldest): Tasks 4, 5 ✓
- Transcriber (load once, language auto): Task 6 ✓
- Output contract (PRD line format, MM:SS.t, [XX], skip empty): Task 3 ✓
- CLI entrypoint with SIGINT, model arg, device arg: Task 7 ✓
- Repo layout (capture/, models/ gitignored, tests/): Task 1 ✓
- Error handling table (mic perm, model missing, queue full, transcribe raises, SIGINT): Tasks 5, 6, 7 ✓
- Manual acceptance test documented: Tasks 1 (README), 7 ✓
- Unit tests for formatter + timing: Tasks 3, 4 ✓
- `backend/` and `ui/` placeholder dirs: **not created in this plan** — they're Step 2's concern; the spec described them as empty placeholders, and creating empty dirs adds clutter with no value. The spec is updated implicitly by deferring this.

**Type consistency:** `Segment(text, start_s, end_s, lang)` used identically in `formatter.py`, `transcribe.py`, `main.py`, and tests. `start_capture(out_queue, stop_event, device)` signature is consistent between definition and call site. `chunk_start_seconds(chunk_index, fresh_samples, overlap_samples)` signature consistent.

**Placeholder scan:** No TBDs, no "handle errors appropriately," every code step contains complete code.
