"""5-gate quality filter for LLM-extracted requirement candidates."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from backend.state import Segment

GateName = Literal["is_requirement", "confidence", "source_quote", "dedup", "schema"]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class FilterConfig:
    confidence_floor: float = field(default_factory=lambda: _env_float("EXTRACTOR_CONFIDENCE_FLOOR", 0.6))
    quote_match_ratio: float = field(default_factory=lambda: _env_float("EXTRACTOR_QUOTE_MATCH_RATIO", 0.75))
    require_source_quote: bool = field(default_factory=lambda: _env_bool("EXTRACTOR_REQUIRE_SOURCE_QUOTE", True))


@dataclass(frozen=True)
class DroppedCandidate:
    gate: GateName
    reason: str
    candidate: dict


@dataclass(frozen=True)
class FilterResult:
    kept: list[dict]
    dropped: list[DroppedCandidate]


_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def _normalize(s: str) -> str:
    return _PUNCT.sub("", s.lower()).strip()


_VALID_CATEGORY = {"functional", "non_functional"}


def _matches_any_segment(quote: str, window: list[Segment], ratio: float) -> bool:
    nq = _normalize(quote)
    if not nq:
        return False
    for seg in window:
        ns = _normalize(seg.text)
        if not ns:
            continue
        if nq in ns:
            return True
        if SequenceMatcher(None, nq, ns).ratio() >= ratio:
            return True
    return False


def filter_candidates(
    candidates: list[dict],
    *,
    window: list[Segment],
    existing_texts: list[str],
    cfg: FilterConfig,
) -> FilterResult:
    kept: list[dict] = []
    dropped: list[DroppedCandidate] = []
    existing_norm = {_normalize(t) for t in existing_texts}

    for c in candidates:
        # Gate 1: is_requirement flag
        if not c.get("is_requirement", False):
            dropped.append(
                DroppedCandidate(gate="is_requirement", reason=str(c.get("reasoning", "")), candidate=c)
            )
            continue

        # Gate 2: confidence
        conf = c.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            conf_f = 0.0
        if conf_f < cfg.confidence_floor:
            dropped.append(
                DroppedCandidate(gate="confidence", reason=f"{conf_f:.2f} < {cfg.confidence_floor}", candidate=c)
            )
            continue

        # Gate 3: source_quote match
        if cfg.require_source_quote:
            quote = str(c.get("source_quote", ""))
            if not _matches_any_segment(quote, window, cfg.quote_match_ratio):
                dropped.append(
                    DroppedCandidate(gate="source_quote", reason="quote not in window", candidate=c)
                )
                continue

        # Gate 4: exact-text dedup
        text = str(c.get("text", "")).strip()
        if _normalize(text) in existing_norm:
            dropped.append(DroppedCandidate(gate="dedup", reason="text exists", candidate=c))
            continue

        # Gate 5: schema sanity
        category = c.get("category")
        language = c.get("language")
        if (
            category not in _VALID_CATEGORY
            or not isinstance(text, str)
            or not text
            or len(text) > 500
            or not isinstance(language, str)
            or len(language) != 2
        ):
            dropped.append(DroppedCandidate(gate="schema", reason="invalid schema", candidate=c))
            continue

        # Survived — strip internal-only fields before returning
        survivor = {k: v for k, v in c.items() if k not in ("is_requirement", "reasoning")}
        survivor["text"] = text
        kept.append(survivor)

    return FilterResult(kept=kept, dropped=dropped)
