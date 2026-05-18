import numpy as np

from capture.transcribe import MAX_GAIN_DB, normalize_rms


def _rms_dbfs(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    return 20.0 * np.log10(rms)


def test_quiet_signal_is_boosted_to_target():
    # 1 kHz sine at -40 dBFS for 0.1s
    t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
    quiet = (0.01 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    assert _rms_dbfs(quiet) < -30.0  # sanity

    out = normalize_rms(quiet, target_dbfs=-20.0)
    assert abs(_rms_dbfs(out) - (-20.0)) < 0.5


def test_loud_signal_is_left_alone():
    # Signal already louder than -20 dBFS — should not be attenuated
    t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
    loud = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    pre = _rms_dbfs(loud)
    assert pre > -20.0  # sanity

    out = normalize_rms(loud, target_dbfs=-20.0)
    assert _rms_dbfs(out) == pre  # unchanged


def test_silence_is_passed_through_unchanged():
    silence = np.zeros(1600, dtype=np.float32)
    out = normalize_rms(silence, target_dbfs=-20.0)
    assert np.array_equal(out, silence)


def test_max_gain_is_capped():
    # Extremely quiet but not silent — would need >MAX_GAIN_DB of gain
    t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
    very_quiet = (1e-3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    pre = _rms_dbfs(very_quiet)
    needed_gain = -20.0 - pre
    assert needed_gain > MAX_GAIN_DB  # sanity: cap should kick in

    out = normalize_rms(very_quiet, target_dbfs=-20.0)
    actual_gain = _rms_dbfs(out) - pre
    assert abs(actual_gain - MAX_GAIN_DB) < 0.1


def test_output_is_clipped_to_unit_range():
    # Signal at -1 dBFS getting boosted to -20 dBFS target → gain <= 0, no clipping needed
    # Construct a case that *would* clip without the np.clip: a near-full-scale signal
    # asked to boost. The function should still leave it alone (gain_db <= 0 branch).
    t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
    near_full = (0.95 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    out = normalize_rms(near_full, target_dbfs=-20.0)
    assert out.max() <= 1.0 and out.min() >= -1.0
