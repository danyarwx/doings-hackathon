from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """A transcribed segment with session-relative timing."""

    text: str
    start_s: float
    end_s: float
    lang: str
    id: str | None = None
    session_id: str | None = None
