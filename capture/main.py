"""Step 1 entrypoint: mic → whisper.cpp → terminal."""

from __future__ import annotations

import argparse
import os
import queue
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from capture.aggregator import ParagraphAggregator
from capture.capture import list_input_devices, start_capture
from capture.formatter import format_segment
from capture.segment import Segment
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
        "--paragraphs",
        action="store_true",
        help="Group consecutive segments into paragraphs split by silence "
        "(experimental — off by default).",
    )
    p.add_argument(
        "--paragraph-gap-s",
        type=float,
        default=1.5,
        help="With --paragraphs: silence (s) between segments that ends a paragraph (default: 1.5).",
    )
    p.add_argument(
        "--max-paragraph-s",
        type=float,
        default=30.0,
        help="With --paragraphs: max paragraph duration before a forced split (default: 30.0).",
    )
    p.add_argument(
        "--api-url",
        default=None,
        help="Backend URL (e.g. http://localhost:8000). When set, each segment is "
        "POSTed to {api_url}/segments fire-and-forget.",
    )
    p.add_argument(
        "--vad-threshold",
        type=float,
        default=-40.0,
        help="Volume threshold in dBFS to trigger recording (default: -40.0).",
    )
    p.add_argument(
        "--vad-silence",
        type=float,
        default=0.5,
        help="Seconds of silence to wait before cutting a chunk (default: 0.4).",
    )
    p.add_argument(
        "--vad-max-duration",
        type=float,
        default=10.0,
        help="Maximum chunk duration in seconds if speech doesn't pause (default: 10.0).",
    )
    p.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    session_id = os.environ.get("CAPTURE_SESSION_ID") or (
        "sess-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    segment_counter = 0

    api_client: httpx.Client | None = None
    if args.api_url:
        api_client = httpx.Client(base_url=args.api_url, timeout=1.0)
        print(f"[main] posting segments to {args.api_url}/segments", file=sys.stderr)
        print(f"[main] session_id={session_id}", file=sys.stderr)

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
    if args.paragraphs:
        aggregator = ParagraphAggregator(
            gap_s=args.paragraph_gap_s,
            max_paragraph_s=args.max_paragraph_s,
        )
        print(
            f"[main] paragraph mode: gap >= {args.paragraph_gap_s:g}s or "
            f"duration > {args.max_paragraph_s:g}s ends a paragraph.",
            file=sys.stderr,
        )

    # In paragraph mode we use ANSI \r + clear-line to redraw the in-progress
    # paragraph on the same terminal row as new segments arrive. When the
    # aggregator closes a paragraph, we commit the line (newline) and start
    # the next one on a fresh row.
    CLEAR_LINE = "\r\033[K"
    tty = sys.stdout.isatty()

    def assign_ids(seg: Segment) -> Segment:
        nonlocal segment_counter
        segment_counter += 1
        return Segment(
            text=seg.text,
            start_s=seg.start_s,
            end_s=seg.end_s,
            lang=seg.lang,
            id=f"seg-{segment_counter:03d}",
            session_id=session_id,
        )

    def post_segment(seg: Segment) -> None:
        if api_client is None:
            return
        try:
            api_client.post(
                "/segments",
                json={
                    "id": seg.id,
                    "session_id": seg.session_id,
                    "text": seg.text,
                    "start_s": seg.start_s,
                    "end_s": seg.end_s,
                    "lang": seg.lang,
                },
            )
        except Exception as exc:
            print(f"[main] POST failed for {seg.id}: {exc}", file=sys.stderr)

    def emit_closed(seg) -> None:
        nonlocal segment_count
        seg = assign_ids(seg)
        line = format_segment(seg)
        if line:
            if tty and aggregator is not None:
                print(CLEAR_LINE + line, flush=True)
            else:
                print(line, flush=True)
            segment_count += 1
        post_segment(seg)

    def render_open(seg) -> None:
        if not tty:
            return
        line = format_segment(seg)
        if line:
            print(CLEAR_LINE + line, end="", flush=True)

    capture_thread = start_capture(
        chunk_queue,
        stop_event,
        device=args.device,
        silence_threshold_dbfs=args.vad_threshold,
        silence_duration_s=args.vad_silence,
        max_duration_s=args.vad_max_duration,
    )
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
                    emit_closed(seg)
                else:
                    for ready in aggregator.add(seg):
                        emit_closed(ready)
                    open_par = aggregator.current()
                    if open_par is not None:
                        if tty:
                            render_open(open_par)
                        else:
                            # No TTY: just print each new segment as it arrives.
                            # We don't accumulate the open paragraph in this mode —
                            # the file output will be the final paragraphs only.
                            pass
    finally:
        stop_event.set()
        if aggregator is not None:
            for ready in aggregator.flush():
                emit_closed(ready)
        if api_client is not None:
            api_client.close()
        capture_thread.join(timeout=2.0)
        elapsed = time.monotonic() - started_at
        print(
            f"[main] stopped. transcribed {segment_count} segments in {elapsed:.1f}s.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
