"""Combine consecutive segments into paragraphs split by silence, language change, or duration."""

from __future__ import annotations

from capture.segment import Segment


class ParagraphAggregator:
    """Buffers segments and emits a merged paragraph when a boundary is reached.

    A boundary fires when:
      - The gap between the new segment's start and the buffer's last end exceeds gap_s.
      - The new segment's language differs from the buffer's language.
      - Adding the new segment would push the paragraph's span past max_paragraph_s.

    `add(seg)` returns the list of paragraphs that just became ready (often empty).
    `flush()` returns any pending paragraph; call once on shutdown.
    """

    def __init__(self, gap_s: float, max_paragraph_s: float) -> None:
        self._gap_s = gap_s
        self._max_paragraph_s = max_paragraph_s
        self._buffer: list[Segment] = []

    def add(self, seg: Segment) -> list[Segment]:
        if not self._buffer:
            self._buffer.append(seg)
            return []

        last = self._buffer[-1]
        first = self._buffer[0]
        gap = seg.start_s - last.end_s
        lang_changed = seg.lang != first.lang
        would_span = seg.end_s - first.start_s

        if gap >= self._gap_s or lang_changed or would_span > self._max_paragraph_s:
            emitted = [self._merge(self._buffer)]
            self._buffer = [seg]
            return emitted

        self._buffer.append(seg)
        return []

    def flush(self) -> list[Segment]:
        if not self._buffer:
            return []
        out = [self._merge(self._buffer)]
        self._buffer = []
        return out

    @staticmethod
    def _merge(segs: list[Segment]) -> Segment:
        text = " ".join(s.text.strip() for s in segs if s.text.strip())
        return Segment(
            text=text,
            start_s=segs[0].start_s,
            end_s=segs[-1].end_s,
            lang=segs[0].lang,
        )
