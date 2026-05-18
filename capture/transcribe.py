"""Whisper.cpp wrapper. Loads the model once; transcribes one chunk per call."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pywhispercpp.model import Model

from capture.segment import Segment

MODELS_DIR = Path(__file__).parent / "models"


class Transcriber:
    def __init__(self, model_name: str = "medium") -> None:
        print(f"[transcribe] loading model '{model_name}'...", file=sys.stderr)
        MODELS_DIR.mkdir(exist_ok=True)
        self._model = Model(
            model=model_name,
            models_dir=str(MODELS_DIR),
            print_realtime=False,
            print_progress=False,
            print_timestamps=False,
        )
        print("[transcribe] model loaded.", file=sys.stderr)

    def transcribe(self, audio: np.ndarray, chunk_start_s: float) -> list[Segment]:
        """Transcribe one chunk and return session-relative segments."""
        raw_segments = self._model.transcribe(audio, language="auto")
        lang = getattr(self._model, "lang_detected", None) or "??"
        out: list[Segment] = []
        for s in raw_segments:
            # pywhispercpp returns t0/t1 in centiseconds.
            start_s = chunk_start_s + s.t0 / 100.0
            end_s = chunk_start_s + s.t1 / 100.0
            out.append(Segment(text=s.text, start_s=start_s, end_s=end_s, lang=lang))
        return out
