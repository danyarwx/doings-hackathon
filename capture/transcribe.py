"""Whisper.cpp wrapper. Loads the model once; transcribes one chunk per call."""

from __future__ import annotations

import sys
from pathlib import Path

import _pywhispercpp as pw
import numpy as np
from pywhispercpp.model import Model

from capture.segment import Segment

MODELS_DIR = Path(__file__).parent / "models"

# Cap normalization gain so we don't amplify pure silence into noise.
MAX_GAIN_DB = 20.0
# Below this RMS we treat the chunk as silence and skip normalization.
SILENCE_RMS_FLOOR = 1e-4


def rms_dbfs(audio: np.ndarray) -> float:
    """Return RMS of audio expressed in dBFS, or -inf for silence."""
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < SILENCE_RMS_FLOOR:
        return float("-inf")
    return 20.0 * np.log10(rms)


def normalize_rms(audio: np.ndarray, target_dbfs: float) -> np.ndarray:
    """Apply gain to bring audio RMS to target_dbfs. No-op on silent chunks."""
    current_dbfs = rms_dbfs(audio)
    if current_dbfs == float("-inf"):
        return audio
    gain_db = min(target_dbfs - current_dbfs, MAX_GAIN_DB)
    if gain_db <= 0:
        # Already at or above target — leave it alone.
        return audio
    gain = 10.0 ** (gain_db / 20.0)
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)


class Transcriber:
    def __init__(
        self,
        model_name: str = "medium",
        language: str | None = None,
        initial_prompt: str | None = None,
        gain_target_dbfs: float | None = -25.0,
        silence_gate_dbfs: float | None = -45.0,
    ) -> None:
        print(f"[transcribe] loading model '{model_name}'...", file=sys.stderr)
        MODELS_DIR.mkdir(exist_ok=True)
        self._model = Model(
            model=model_name,
            models_dir=str(MODELS_DIR),
            print_realtime=False,
            print_progress=False,
            print_timestamps=False,
        )
        self._forced_language = language
        self._initial_prompt = initial_prompt
        self._gain_target_dbfs = gain_target_dbfs
        self._silence_gate_dbfs = silence_gate_dbfs
        if language:
            print(f"[transcribe] language forced to '{language}'.", file=sys.stderr)
        if initial_prompt:
            preview = initial_prompt if len(initial_prompt) <= 80 else initial_prompt[:77] + "..."
            print(f"[transcribe] initial_prompt: {preview!r}", file=sys.stderr)
        if gain_target_dbfs is not None:
            print(
                f"[transcribe] RMS-normalizing chunks to {gain_target_dbfs:g} dBFS "
                f"(max gain {MAX_GAIN_DB:g} dB).",
                file=sys.stderr,
            )
        if silence_gate_dbfs is not None:
            print(
                f"[transcribe] silence gate at {silence_gate_dbfs:g} dBFS.",
                file=sys.stderr,
            )
        print("[transcribe] model loaded.", file=sys.stderr)

    def transcribe(self, audio: np.ndarray, chunk_start_s: float) -> list[Segment]:
        """Transcribe one chunk and return session-relative segments."""
        # Silence gate uses pre-normalization RMS so quiet noise can't sneak through.
        if self._silence_gate_dbfs is not None:
            if rms_dbfs(audio) < self._silence_gate_dbfs:
                return []

        if self._gain_target_dbfs is not None:
            audio = normalize_rms(audio, self._gain_target_dbfs)

        params: dict = {}
        if self._initial_prompt:
            params["initial_prompt"] = self._initial_prompt
        if self._forced_language:
            params["language"] = self._forced_language

        raw_segments = self._model.transcribe(audio, **params)

        if self._forced_language:
            lang = self._forced_language
        else:
            lang_id = pw.whisper_full_lang_id(self._model._ctx)
            lang = pw.whisper_lang_str(lang_id) if lang_id >= 0 else "??"

        out: list[Segment] = []
        for s in raw_segments:
            # pywhispercpp returns t0/t1 in centiseconds.
            start_s = chunk_start_s + s.t0 / 100.0
            end_s = chunk_start_s + s.t1 / 100.0
            out.append(Segment(text=s.text, start_s=start_s, end_s=end_s, lang=lang))
        return out
