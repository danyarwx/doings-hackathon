"""In-memory session state for the backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backend.insights import Insight

RecordingState = Literal["idle", "recording", "paused", "stopping"]
DeliveryStatusValue = Literal["pending", "delivered", "failed"]


@dataclass(frozen=True)
class Segment:
    id: str
    session_id: str
    text: str
    start_s: float
    end_s: float
    lang: str


@dataclass(frozen=True)
class DeliveryStatus:
    id: str
    status: DeliveryStatusValue
    attempts: int


@dataclass
class SessionState:
    recording_state: RecordingState = "idle"
    session_id: str | None = None
    segments: list[Segment] = field(default_factory=list)
    deliveries: dict[str, DeliveryStatus] = field(default_factory=dict)
    insights: list[Insight] = field(default_factory=list)
    # Step-4 export: dict shape {"requirements": [...], "decisions": [...]}
    # produced by POST /export/generate. None until generated; cleared on the
    # next /control/start.
    export_draft: dict | None = None

    def add_segment(self, seg: Segment) -> None:
        self.segments.append(seg)
        self.deliveries[seg.id] = DeliveryStatus(id=seg.id, status="pending", attempts=0)
        if self.session_id is None:
            self.session_id = seg.session_id

    def update_delivery(self, seg_id: str, status: DeliveryStatusValue, attempts: int) -> None:
        self.deliveries[seg_id] = DeliveryStatus(id=seg_id, status=status, attempts=attempts)

    def delivered_count(self) -> int:
        return sum(1 for d in self.deliveries.values() if d.status == "delivered")

    def reset(self, session_id: str | None = None) -> None:
        self.segments = []
        self.deliveries = {}
        self.insights = []
        self.export_draft = None
        self.session_id = session_id
        self.recording_state = "idle"
