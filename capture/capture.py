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
