"""Insight model (LLM-extracted requirement candidate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InsightType = Literal["requirement", "action_item", "decision"]
InsightStatus = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class Insight:
    id: str
    session_id: str
    type: InsightType
    text: str
    source_quote: str
    language: str
    confidence: float
    needs_review: bool
    status: InsightStatus
    created_at_iso: str
