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
