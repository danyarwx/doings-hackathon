"""Aggregates whisper Segments into coherent Utterances for the LLM extractor.

Flushes when any of these fire:
  1. Silence gap to next segment > BUFFER_MAX_SILENCE_S (the triggering segment
     starts the *next* buffer; it is not included in the flush).
  2. A noise-only segment arrives ([BLANK_AUDIO], "(crowd chattering)", "[music]"
     etc.) — whisper emits these when it hears no speech, so we treat them as
     the speaker stopping. The noise segment itself is dropped.
  3. Buffer duration reaches BUFFER_MAX_DURATION_S.

We deliberately do NOT flush on terminal punctuation. Whisper appends "." at
every ~2s chunk boundary regardless of whether the sentence has ended, so
punctuation is not a reliable boundary signal.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import Counter
from dataclasses import dataclass

from backend.state import Segment


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


DEFAULT_MAX_SILENCE_S = _env_float("BUFFER_MAX_SILENCE_S", 1.5)
DEFAULT_MAX_DURATION_S = _env_float("BUFFER_MAX_DURATION_S", 20.0)


@dataclass(frozen=True)
class Utterance:
    text: str
    start_s: float
    end_s: float
    lang: str
    segment_ids: list[str]


# Whisper's "no speech" audio descriptors: [BLANK_AUDIO], (crowd chattering),
# [music], (typing), * sighs *, etc. Matches when the entire stripped text is
# wrapped in (), [], or *…*. These are not transcribed speech — treat them as
# a pause signal and drop the segment.
_NOISE_RE = re.compile(r"^\s*[\(\[\*][^()\[\]\*]*[\)\]\*]\s*$")


def _is_noise(seg: Segment) -> bool:
    t = seg.text.strip()
    if not t:
        return True
    return bool(_NOISE_RE.match(t))


def _majority_lang(segments: list[Segment]) -> str:
    counts = Counter(s.lang for s in segments)
    top = counts.most_common()
    # Ties: the first segment's lang wins.
    if len(top) > 1 and top[0][1] == top[1][1]:
        return segments[0].lang
    return top[0][0]


class SentenceBuffer:
    """Producer side: receives Segments via add(), emits Utterances on queue."""

    def __init__(
        self,
        *,
        max_silence_s: float = DEFAULT_MAX_SILENCE_S,
        max_duration_s: float = DEFAULT_MAX_DURATION_S,
    ) -> None:
        self._max_silence_s = max_silence_s
        self._max_duration_s = max_duration_s
        self._pending: list[Segment] = []
        self.queue: asyncio.Queue[Utterance] = asyncio.Queue()

    async def add(self, seg: Segment) -> None:
        # Noise / blank-audio segments are treated as a pause: flush whatever
        # was buffered, then drop the noise segment itself.
        if _is_noise(seg):
            await self._flush()
            return

        # Silence-gap check fires BEFORE appending the new segment.
        if self._pending:
            gap = seg.start_s - self._pending[-1].end_s
            if gap > self._max_silence_s:
                await self._flush()

        self._pending.append(seg)

        # Max-duration flush after appending. Whisper emits "." at every chunk
        # boundary, so we deliberately do NOT flush on terminal punctuation —
        # silence gaps and the hard duration cap are the only triggers.
        if self._current_duration() >= self._max_duration_s:
            await self._flush()

    def reset(self) -> None:
        self._pending = []
        # Drain pending utterances so the consumer doesn't see stale data.
        try:
            while True:
                self.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    def _current_duration(self) -> float:
        if not self._pending:
            return 0.0
        return self._pending[-1].end_s - self._pending[0].start_s

    async def _flush(self) -> None:
        if not self._pending:
            return
        segs = self._pending
        self._pending = []
        text = " ".join(s.text.strip() for s in segs).strip()
        if not text:
            return
        u = Utterance(
            text=text,
            start_s=segs[0].start_s,
            end_s=segs[-1].end_s,
            lang=_majority_lang(segs),
            segment_ids=[s.id for s in segs],
        )
        await self.queue.put(u)
