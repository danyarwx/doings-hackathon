"""Step 1 entrypoint: mic → whisper.cpp → terminal."""

from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
import time
from pathlib import Path

from capture.aggregator import ParagraphAggregator
from capture.capture import list_input_devices, start_capture
from capture.formatter import format_segment
from capture.transcribe import Transcriber


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local live STT to the terminal.")
    p.add_argument("--model", default="medium", help="Whisper model (default: medium)")
    p.add_argument("--device", type=int, default=None, help="Input device index")
    p.add_argument(
        "--language",
        default=None,
        help="Force language code (e.g. 'de', 'en'). Default: auto-detect per chunk.",
    )
    p.add_argument(
        "--prompt",
        default=None,
        help="Vocabulary hint string passed to whisper as initial_prompt "
        "(e.g. 'OAuth 2.0, REST, Kubernetes, Telekom').",
    )
    p.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help="Read vocabulary hint from a file (overrides --prompt).",
    )
    p.add_argument(
        "--gain-target-dbfs",
        type=float,
        default=-25.0,
        help="RMS-normalize each chunk to this dBFS level before transcribing "
        "(default: -25.0). Lower = less boost, less noise hallucination.",
    )
    p.add_argument(
        "--no-normalize",
        action="store_true",
        help="Disable RMS normalization (overrides --gain-target-dbfs).",
    )
    p.add_argument(
        "--silence-gate-dbfs",
        type=float,
        default=-45.0,
        help="Skip transcribing chunks whose RMS is below this dBFS "
        "(default: -45.0). Prevents noise hallucinations like '[sigh]'. "
        "Set higher to gate more aggressively.",
    )
    p.add_argument(
        "--no-silence-gate",
        action="store_true",
        help="Disable the silence gate (transcribe every chunk).",
    )
    p.add_argument(
        "--paragraph-gap-s",
        type=float,
        default=1.5,
        help="Silence (seconds) between segments that ends a paragraph (default: 1.5).",
    )
    p.add_argument(
        "--max-paragraph-s",
        type=float,
        default=30.0,
        help="Maximum paragraph duration before a forced split (default: 30.0).",
    )
    p.add_argument(
        "--no-paragraphs",
        action="store_true",
        help="Disable paragraph grouping; print one line per raw whisper segment.",
    )
    p.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_devices:
        for idx, name in list_input_devices():
            print(f"{idx}: {name}")
        return 0

    if args.prompt_file:
        initial_prompt = args.prompt_file.read_text().strip()
    else:
        initial_prompt = args.prompt

    gain_target = None if args.no_normalize else args.gain_target_dbfs
    silence_gate = None if args.no_silence_gate else args.silence_gate_dbfs

    transcriber = Transcriber(
        model_name=args.model,
        language=args.language,
        initial_prompt=initial_prompt,
        gain_target_dbfs=gain_target,
        silence_gate_dbfs=silence_gate,
    )

    chunk_queue: "queue.Queue[tuple[float, object]]" = queue.Queue(maxsize=8)
    stop_event = threading.Event()

    def handle_sigint(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    aggregator = None
    if not args.no_paragraphs:
        aggregator = ParagraphAggregator(
            gap_s=args.paragraph_gap_s,
            max_paragraph_s=args.max_paragraph_s,
        )
        print(
            f"[main] paragraph mode: gap >= {args.paragraph_gap_s:g}s or "
            f"duration > {args.max_paragraph_s:g}s ends a paragraph.",
            file=sys.stderr,
        )

    def emit(seg) -> None:
        nonlocal segment_count
        line = format_segment(seg)
        if line:
            print(line, flush=True)
            segment_count += 1

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
                if aggregator is None:
                    emit(seg)
                else:
                    for ready in aggregator.add(seg):
                        emit(ready)
    finally:
        stop_event.set()
        if aggregator is not None:
            for ready in aggregator.flush():
                emit(ready)
        capture_thread.join(timeout=2.0)
        elapsed = time.monotonic() - started_at
        print(
            f"[main] stopped. transcribed {segment_count} segments in {elapsed:.1f}s.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
