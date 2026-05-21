"""Microphone capture: emits fixed-size chunks with overlap into a queue."""

from __future__ import annotations

import queue
import sys
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CALLBACK_BLOCKSIZE = 1600  # 100ms

def rms_dbfs(audio: np.ndarray) -> float:
    """Return RMS of audio in dBFS."""
    if len(audio) == 0:
        return float("-inf")
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < 1e-4:
        return float("-inf")
    return 20.0 * np.log10(rms)


def start_capture(
    out_queue: "queue.Queue[tuple[float, np.ndarray]]",
    stop_event: threading.Event,
    device: int | None = None,
    silence_threshold_dbfs: float = -40.0,
    silence_duration_s: float = 0.5,
    preroll_s: float = 0.3,
    max_duration_s: float = 10.0,
    overlap_s: float = 0.5,
) -> threading.Thread:
    """Start a VAD background thread capturing mic audio and pushing dynamic chunks.
    
    Uses a state machine to detect voice activity. Emits a chunk when speech stops
    (silence_duration_s) or reaches max_duration_s. Includes preroll_s of audio 
    before the threshold was crossed to avoid clipping the start of words.
    """
    
    preroll_max_blocks = int((preroll_s * SAMPLE_RATE) / CALLBACK_BLOCKSIZE)
    silence_max_blocks = int((silence_duration_s * SAMPLE_RATE) / CALLBACK_BLOCKSIZE)
    max_chunk_samples = int(max_duration_s * SAMPLE_RATE)
    overlap_samples = int(overlap_s * SAMPLE_RATE)

    def run() -> None:
        is_recording = False
        silence_blocks = 0
        total_samples_processed = 0
        chunk_start_sample = 0
        
        # Using lists of arrays is much faster than repeatedly concatenating numpy arrays
        buffer: list[np.ndarray] = []
        preroll_buffer: list[np.ndarray] = []
        
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

                block_samples = len(block)
                volume = rms_dbfs(block)
                is_speech = volume > silence_threshold_dbfs

                if not is_recording:
                    if is_speech:
                        # State Change: Start Recording
                        is_recording = True
                        silence_blocks = 0
                        preroll_samples_count = sum(len(b) for b in preroll_buffer)
                        chunk_start_sample = total_samples_processed - preroll_samples_count
                        buffer = preroll_buffer + [block]
                        preroll_buffer = []
                    else:
                        # Still Silent: Maintain the rolling preroll buffer
                        preroll_buffer.append(block)
                        if len(preroll_buffer) > preroll_max_blocks:
                            preroll_buffer.pop(0)
                else:
                    # We are currently recording a phrase
                    buffer.append(block)
                    if not is_speech:
                        silence_blocks += 1
                    else:
                        silence_blocks = 0
                        
                    current_chunk_len = sum(len(b) for b in buffer)
                    
                    # State Change: Stop Recording if silent for too long, or chunk is too big
                    if silence_blocks >= silence_max_blocks or current_chunk_len >= max_chunk_samples:
                        chunk = np.concatenate(buffer)
                        start_s = max(0.0, chunk_start_sample / SAMPLE_RATE)
                        
                        try:
                            out_queue.put_nowait((start_s, chunk))
                        except queue.Full:
                            try:
                                out_queue.get_nowait()
                                out_queue.put_nowait((start_s, chunk))
                                print("[capture] queue full — dropped oldest chunk", file=sys.stderr)
                            except queue.Empty:
                                pass
                                
                        if silence_blocks >= silence_max_blocks:
                            # Natural break: The user stopped talking.
                            is_recording = False
                            silence_blocks = 0
                            preroll_buffer = buffer[-preroll_max_blocks:] if preroll_max_blocks > 0 else []
                            buffer = []
                        else:
                            # Forced break: User is still talking, but we want to forward the text!
                            # Keep the last `overlap_s` of audio in the buffer for AI context.
                            tail = chunk[-overlap_samples:] if len(chunk) > overlap_samples else chunk
                            buffer = [tail]
                            silence_blocks = 0
                            # Advance the start timestamp by the amount of audio we actually consumed
                            chunk_start_sample += (len(chunk) - len(tail))

                # Always tick the clock forward, even during silence, to keep timestamps perfectly accurate
                total_samples_processed += block_samples

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
