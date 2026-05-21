"""Quality filter for LLM-extracted requirement candidates.

Gates, in order:
  1. is_requirement  — LLM's own self-assessment must be True
  2. length          — text.strip() length >= EXTRACTOR_MIN_TEXT_LEN
  3. verb            — text must contain a modal or intent verb (EN+DE)
  4. source_quote    — quote must (fuzzy-)match a span in the focus utterance
  5. dedupe          — text must not fuzzy-match (>= ratio) any existing text
  6. schema          — category, language, certainty in allowed sets
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from backend.sentence_buffer import Utterance

GateName = Literal["length", "verb", "source_quote", "dedupe", "schema"]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class FilterConfig:
    min_text_len: int = field(default_factory=lambda: _env_int("EXTRACTOR_MIN_TEXT_LEN", 30))
    verb_gate: bool = field(default_factory=lambda: _env_bool("EXTRACTOR_VERB_GATE", True))
    quote_match_ratio: float = field(default_factory=lambda: _env_float("EXTRACTOR_QUOTE_MATCH_RATIO", 0.6))
    dedupe_ratio: float = field(default_factory=lambda: _env_float("EXTRACTOR_DEDUPE_RATIO", 0.85))


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
_VALID_CERTAINTY = {"explicit", "implied"}

# Word-boundary, case-insensitive. Multi-word forms ("needs to", "has to") use
# explicit spacing; single tokens use \b boundaries.
_VERB_PATTERNS = [
    # English modal
    r"\bmust\b", r"\bshall\b", r"\bshould\b", r"\bwill\b",
    r"\bneeds?\s+to\b", r"\bhas\s+to\b", r"\bhave\s+to\b",
    # English intent
    r"\bneed\b", r"\bwant\b", r"\badd\b", r"\bshow\b",
    r"\bsupport\b", r"\ballow\b", r"\bintegrate\b",
    # German modal (incl. plural / subjunctive / past-participle forms)
    r"\bmuss\b", r"\bm[üu]ssen\b", r"\bm[üu]sste\b", r"\bm[üu]ssten\b",
    r"\bsoll\b", r"\bsollte\b", r"\bsollten\b", r"\bsollen\b",
    r"\bwird\b", r"\bwerden\b", r"\bwerde\b",
    r"\bbraucht\b", r"\bbrauchen\b",
    r"\bm[öo]chte\b", r"\bm[öo]chten\b",
    r"\bkann\b", r"\bkönnen\b", r"\bkönnte\b", r"\bkönnten\b",
    # German intent
    r"\bwollen\b", r"\bwill\b",
    r"\bhinzufügen\b", r"\bzeigen\b", r"\bunterstützen\b",
    r"\bbereitstellen\b", r"\bbereit\s+stellen\b",
    r"\bintegrieren\b", r"\bentwickeln\b", r"\bimplementieren\b",
    r"\bbauen\b", r"\bbieten\b", r"\berlauben\b",
    r"\beinführen\b", r"\bermöglichen\b",
]
_VERB_RE = re.compile("|".join(_VERB_PATTERNS), re.IGNORECASE | re.UNICODE)


def _contains_verb(text: str) -> bool:
    return bool(_VERB_RE.search(text))


def _matches_focus(quote: str, focus: Utterance, ratio: float) -> bool:
    nq = _normalize(quote)
    if not nq:
        return False
    ns = _normalize(focus.text)
    if not ns:
        return False
    if nq in ns:
        return True
    # Whole-quote fuzzy match.
    if SequenceMatcher(None, nq, ns).ratio() >= ratio:
        return True
    # Small models paraphrase. Accept if any 5+-word window of the quote
    # appears verbatim in the focus — that's enough grounding to trust it.
    words = nq.split()
    if len(words) >= 5:
        for i in range(len(words) - 4):
            chunk = " ".join(words[i : i + 5])
            if chunk in ns:
                return True
    return False


def _is_near_duplicate(text: str, existing_texts: list[str], ratio: float) -> bool:
    nt = _normalize(text)
    if not nt:
        return False
    for ex in existing_texts:
        ne = _normalize(ex)
        if not ne:
            continue
        if SequenceMatcher(None, nt, ne).ratio() >= ratio:
            return True
    return False


def filter_candidates(
    candidates: list[dict],
    *,
    focus: Utterance,
    existing_texts: list[str],
    cfg: FilterConfig,
) -> FilterResult:
    kept: list[dict] = []
    dropped: list[DroppedCandidate] = []

    for c in candidates:
        text = str(c.get("text", "")).strip()

        # Gate 1: length
        if len(text) < cfg.min_text_len:
            dropped.append(DroppedCandidate(
                gate="length", reason=f"{len(text)} < {cfg.min_text_len}", candidate=c,
            ))
            continue

        # Gate 2: verb
        if cfg.verb_gate and not _contains_verb(text):
            dropped.append(DroppedCandidate(
                gate="verb", reason="no modal/intent verb", candidate=c,
            ))
            continue

        # Gate 3: source_quote (always on)
        quote = str(c.get("source_quote", ""))
        if not _matches_focus(quote, focus, cfg.quote_match_ratio):
            dropped.append(DroppedCandidate(
                gate="source_quote", reason="quote not in focus", candidate=c,
            ))
            continue

        # Gate 4: fuzzy dedupe
        if _is_near_duplicate(text, existing_texts, cfg.dedupe_ratio):
            dropped.append(DroppedCandidate(
                gate="dedupe", reason="near-duplicate of existing", candidate=c,
            ))
            continue

        # Gate 5: schema sanity
        category = c.get("category")
        certainty = c.get("certainty")
        language = c.get("language")
        if (
            category not in _VALID_CATEGORY
            or certainty not in _VALID_CERTAINTY
            or not isinstance(language, str)
            or len(language) != 2
            or len(text) > 500
        ):
            dropped.append(DroppedCandidate(
                gate="schema", reason="invalid schema", candidate=c,
            ))
            continue

        survivor = {k: v for k, v in c.items() if k not in ("is_requirement", "reasoning")}
        survivor["text"] = text
        kept.append(survivor)

    return FilterResult(kept=kept, dropped=dropped)
