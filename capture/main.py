"""Step 1 entrypoint: mic → whisper.cpp → terminal."""

from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
import time
from pathlib import Path

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
        default=-20.0,
        help="RMS-normalize each chunk to this dBFS level before transcribing "
        "(default: -20.0). Set to a positive number or 'inf' to disable.",
    )
    p.add_argument(
        "--no-normalize",
        action="store_true",
        help="Disable RMS normalization (overrides --gain-target-dbfs).",
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

    transcriber = Transcriber(
        model_name=args.model,
        language=args.language,
        initial_prompt=initial_prompt,
        gain_target_dbfs=gain_target,
    )

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
