"""Insight model (LLM-extracted requirement candidate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InsightStatus = Literal["pending", "approved", "declined"]
InsightCategory = Literal["functional", "non_functional"]
InsightCertainty = Literal["explicit", "implied"]


@dataclass(frozen=True)
class Insight:
    id: str
    session_id: str
    category: InsightCategory
    certainty: InsightCertainty
    text: str
    original_text: str
    source_quote: str
    language: str
    status: InsightStatus
    created_at_iso: str
