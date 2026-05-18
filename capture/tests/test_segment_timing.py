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
