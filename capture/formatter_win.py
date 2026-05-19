from typing import Optional

from capture.segment import Segment


def _fmt_ts(seconds: float) -> str:
    """Format seconds as MM:SS.t (one decimal). Minutes can exceed 59."""
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes:02d}:{remaining:04.1f}"


def format_segment(seg: Segment) -> Optional[str]:
    """Return the PRD line format, or None if the segment text is empty/whitespace."""
    text = seg.text.strip()
    if not text:
        return None
    return f"[{_fmt_ts(seg.start_s)} -> {_fmt_ts(seg.end_s)}] [{seg.lang.upper()}] {text}"
