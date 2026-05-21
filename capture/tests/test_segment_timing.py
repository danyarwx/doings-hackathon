"""VAD refactor (b5ecfeab) replaced fixed-cadence chunking with a state
machine driven by RMS dBFS thresholds, so chunk start times are no longer
derivable from a closed-form helper. The replaced helper had a tested
contract; the new behavior is exercised by the integration loop, so here
we just cover the tiny RMS primitive that the state machine relies on."""

import math

import numpy as np

from capture.capture import rms_dbfs


def test_rms_of_empty_array_is_negative_infinity():
    assert rms_dbfs(np.zeros(0, dtype=np.float32)) == float("-inf")


def test_rms_of_silence_is_negative_infinity():
    silence = np.zeros(1600, dtype=np.float32)
    assert rms_dbfs(silence) == float("-inf")


def test_rms_of_full_scale_sine_is_about_minus_3_dbfs():
    # A full-scale ±1.0 sine has RMS ≈ 0.707 → ≈ -3 dBFS.
    t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
    sine = np.sin(2 * math.pi * 440 * t).astype(np.float32)
    db = rms_dbfs(sine)
    assert -3.5 < db < -2.5


def test_rms_of_quiet_audio_is_low():
    # -40 dBFS amplitude sine.
    t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
    sine = (0.01 * np.sin(2 * math.pi * 440 * t)).astype(np.float32)
    db = rms_dbfs(sine)
    assert db < -30.0
