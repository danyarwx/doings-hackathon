# Step 3 Quality Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Step-3 live extractor (fragment slop + duplicates) with a sentence-buffered, event-driven pipeline plus a stricter prompt and harder filter gates.

**Architecture:** A new `SentenceBuffer` collapses whisper's 2s segments into coherent `Utterance`s (flush on `.!?`, silence >1.5s, or 20s max). The `ExtractorWorker` drops its 5s tick and consumes utterances from an `asyncio.Queue` — each utterance is the FOCUS, the last 3 prior utterances are CONTEXT. The prompt is rewritten with BAD/GOOD few-shot examples and a modal-or-intent-verb rule; `confidence: float` becomes `certainty: "explicit"|"implied"`. Filter gates: length ≥40, verb regex (EN+DE), source-quote fuzzy match, fuzzy dedupe ≥0.85.

**Tech Stack:** Python 3.10+, FastAPI, asyncio, httpx, pytest. Frontend: React 18 + TypeScript + Tailwind.

**Spec:** [docs/superpowers/specs/2026-05-20-step3-quality-pass-design.md](../specs/2026-05-20-step3-quality-pass-design.md)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/sentence_buffer.py` | Create | `Utterance` dataclass + `SentenceBuffer` async producer |
| `backend/insights.py` | Modify | Replace `confidence: float` with `certainty: Literal["explicit","implied"]` |
| `backend/extractor_prompt.py` | Rewrite | New definition, schema (certainty), few-shot block, FOCUS+CONTEXT layout |
| `backend/extractor_filter.py` | Rewrite | New gates: length → verb → quote → fuzzy-dedupe → schema |
| `backend/extractor.py` | Rewrite | Event-driven worker consuming `asyncio.Queue[Utterance]`, FOCUS+CONTEXT prompt |
| `backend/server.py` | Modify | Plumb buffer/queue; update `_insight_to_dict`; remove `confidence` from API responses |
| `ui/src/lib/types.ts` | Modify | `confidence: number` → `certainty: "explicit"\|"implied"` on `Insight` |
| `ui/src/components/InsightCard.tsx` | Modify | Render certainty badge instead of % number |
| `backend/tests/test_sentence_buffer.py` | Create | Buffer flush rules + edge cases |
| `backend/tests/test_extractor_filter.py` | Rewrite | New gate tests |
| `backend/tests/test_extractor.py` | Rewrite | Queue-driven dispatch + skip-if-busy + context window |
| `backend/tests/test_extractor_prompt.py` | Modify | Schema + few-shot assertions |
| `backend/tests/test_insights_model.py` | Modify | `certainty` field |
| `backend/tests/test_insights_api.py` | Modify | API response shape |
| `README.md` | Modify | Env var table + tunables |

---

## Task 1: `Utterance` model and `SentenceBuffer`

**Files:**
- Create: `backend/sentence_buffer.py`
- Test: `backend/tests/test_sentence_buffer.py`

- [ ] **Step 1.1: Write failing tests**

Create `backend/tests/test_sentence_buffer.py`:

```python
import asyncio
import pytest
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import Segment


def _seg(id_: str, text: str, start: float, end: float, lang: str = "en") -> Segment:
    return Segment(id=id_, session_id="s1", text=text, start_s=start, end_s=end, lang=lang)


@pytest.mark.asyncio
async def test_flush_on_terminal_punctuation():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "The dashboard must show", 0.0, 2.0))
    assert buf.queue.empty()
    await buf.add(_seg("s2", "monthly revenue.", 2.0, 4.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "The dashboard must show monthly revenue."
    assert u.start_s == 0.0
    assert u.end_s == 4.0
    assert u.segment_ids == ["s1", "s2"]
    assert u.lang == "en"


@pytest.mark.asyncio
async def test_flush_on_silence_gap():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "We need German support", 0.0, 2.0))
    # Next segment starts 2.0s later (gap > 1.5)
    await buf.add(_seg("s2", "and a dashboard", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "We need German support"
    assert u.segment_ids == ["s1"]
    # s2 is now the start of a new buffer; no flush yet
    assert buf.queue.empty()


@pytest.mark.asyncio
async def test_flush_on_max_duration():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=5.0)
    await buf.add(_seg("s1", "long monologue starts", 0.0, 2.0))
    await buf.add(_seg("s2", "and keeps going", 2.0, 4.0))
    await buf.add(_seg("s3", "without any breaks", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "long monologue starts and keeps going without any breaks"
    assert u.end_s - u.start_s >= 5.0


@pytest.mark.asyncio
async def test_blank_audio_segment_dropped():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "[BLANK_AUDIO]", 0.0, 2.0))
    await buf.add(_seg("s2", "", 2.0, 4.0))
    await buf.add(_seg("s3", "real content.", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "real content."
    assert u.segment_ids == ["s3"]


@pytest.mark.asyncio
async def test_reset_discards_pending():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "partial thought", 0.0, 2.0))
    buf.reset()
    # Adding a new segment after reset should start fresh, no flush
    await buf.add(_seg("s2", "new sentence.", 0.0, 2.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.segment_ids == ["s2"]


@pytest.mark.asyncio
async def test_majority_lang_with_first_on_tie():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "Wir brauchen", 0.0, 2.0, lang="de"))
    await buf.add(_seg("s2", "support.", 2.0, 4.0, lang="en"))
    # 1 de + 1 en → tie → first wins
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.lang == "de"
```

- [ ] **Step 1.2: Verify tests fail**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_sentence_buffer.py -v`
Expected: `ModuleNotFoundError: No module named 'backend.sentence_buffer'`

- [ ] **Step 1.3: Implement `SentenceBuffer`**

Create `backend/sentence_buffer.py`:

```python
"""Aggregates whisper Segments into coherent Utterances for the LLM extractor.

Flushes when any of these fire:
  1. Buffer's concatenated text ends in . ! ?
  2. Silence gap to next segment > BUFFER_MAX_SILENCE_S (the triggering segment
     starts the *next* buffer; it is not included in the flush).
  3. Buffer duration reaches BUFFER_MAX_DURATION_S.

Blank-audio segments (text="" or "[BLANK_AUDIO]") are dropped.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass
from typing import Optional

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


def _is_blank(seg: Segment) -> bool:
    t = seg.text.strip()
    return not t or t == "[BLANK_AUDIO]"


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))


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
        if _is_blank(seg):
            return

        # Silence-gap check fires BEFORE appending the new segment.
        if self._pending:
            gap = seg.start_s - self._pending[-1].end_s
            if gap > self._max_silence_s:
                await self._flush()

        self._pending.append(seg)

        # Punctuation or max-duration flush after appending.
        if _ends_sentence(seg.text) or self._current_duration() >= self._max_duration_s:
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
```

- [ ] **Step 1.4: Verify tests pass**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_sentence_buffer.py -v`
Expected: 6 passed.

- [ ] **Step 1.5: Commit**

```bash
git add backend/sentence_buffer.py backend/tests/test_sentence_buffer.py
git commit -m "feat(backend): SentenceBuffer aggregates segments into Utterances"
```

---

## Task 2: Schema change — `confidence` → `certainty`

**Files:**
- Modify: `backend/insights.py`
- Modify: `backend/tests/test_insights_model.py`
- Modify: `backend/tests/test_insights_api.py` (any test asserting `confidence` field)
- Modify: `ui/src/lib/types.ts`

This is intentionally a single atomic schema change; later tasks rely on it.

- [ ] **Step 2.1: Update `Insight` dataclass**

Replace `backend/insights.py` contents with:

```python
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
```

- [ ] **Step 2.2: Update `ui/src/lib/types.ts`**

In the `Insight` type, replace `confidence: number;` with `certainty: "explicit" | "implied";`.

The relevant lines after change should be:

```ts
export type InsightCertainty = "explicit" | "implied";

export type Insight = {
  id: string;
  session_id: string;
  category: InsightCategory;
  certainty: InsightCertainty;
  text: string;
  original_text: string;
  source_quote: string;
  language: string;
  status: InsightStatus;
  created_at_iso: string;
};
```

- [ ] **Step 2.3: Update tests for the new field**

In `backend/tests/test_insights_model.py`, replace every occurrence of `confidence=0.<x>` with `certainty="explicit"` (or `"implied"` if the test name implies inference). Re-read the file with `Read` first, then `Edit`.

In `backend/tests/test_insights_api.py`, do the same — search for `confidence` and switch to `certainty`. Any test that asserted on `confidence` in the API response should now assert on `certainty`.

- [ ] **Step 2.4: Run targeted tests (expect compile errors elsewhere — that's fine)**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_insights_model.py backend/tests/test_insights_api.py -v`
Expected: PASS for these two files. Other files will be fixed in later tasks.

- [ ] **Step 2.5: Commit**

```bash
git add backend/insights.py backend/tests/test_insights_model.py backend/tests/test_insights_api.py ui/src/lib/types.ts
git commit -m "refactor: replace Insight.confidence (float) with certainty (explicit|implied)"
```

---

## Task 3: Prompt rewrite — FOCUS + CONTEXT layout, modal/intent verb rule, few-shot

**Files:**
- Modify: `backend/extractor_prompt.py`
- Modify: `backend/tests/test_extractor_prompt.py`

- [ ] **Step 3.1: Replace `backend/extractor_prompt.py`**

```python
"""Prompt builder for the requirements-extractor LLM.

The LLM sees one FOCUS utterance and up to 3 CONTEXT utterances. It extracts
requirements ONLY from the FOCUS; CONTEXT is for resolving pronouns/references.
"""

from __future__ import annotations

from backend.sentence_buffer import Utterance

SYSTEM_PROMPT = """You are a requirements extractor for engineering meetings. Output ONLY valid JSON matching the schema — no prose, no markdown, no comments.

A REQUIREMENT is a COMPLETE CLAUSE (subject + verb) containing EITHER:
- a MODAL verb of obligation: must, shall, should, will, needs to, has to, muss, soll, wird, braucht; OR
- a clear INTENT verb: need, want, add, show, support, allow, integrate, brauchen, wollen, hinzufügen, zeigen, unterstützen.

The clause must describe what the system or product does, supports, or enforces.

DO NOT EXTRACT:
- Fragments, noun phrases, or incomplete clauses
- Questions ("how many?"), opinions, agreements ("yeah", "ok"), or chatter
- Items already listed under EXISTING (do not duplicate)
- Hypotheticals or aside speculation ("maybe we could…")
- Implementation chatter unless it encodes a real constraint
- Anything not present in the FOCUS utterance — CONTEXT is read-only

BAD examples (every one of these MUST be rejected by setting is_requirement=false):
- "product requirements" — noun phrase, no verb
- "document for the new" — fragment, incomplete clause
- "how many?" — question, not a directive
- "Yeah." — chatter
- "It would be sales made." — ambiguous fragment, no clear requirement

GOOD examples (these are real requirements):
- "The dashboard must show monthly revenue." — modal verb + complete clause → explicit
- "We need to support German language input." — intent verb + complete clause → explicit
- "Sales reports should export to CSV." — modal verb + complete clause → explicit

For each candidate, INCLUDE an `is_requirement` boolean and a one-sentence `reasoning`. If `is_requirement` is false, still include the entry so the filter can log it.

`source_quote` MUST be the exact words copied from the FOCUS utterance — no paraphrasing.

`certainty` is "explicit" if the FOCUS utterance contains the modal/intent verb verbatim, or "implied" if you inferred the requirement using CONTEXT (e.g., resolved a pronoun).

Output the requirement `text` in the same language as the FOCUS (de stays de, en stays en).

SCHEMA
{
  "requirements": [
    {
      "is_requirement": true | false,
      "reasoning": "<one sentence>",
      "text": "<requirement in source language, complete clause, ≥40 chars>",
      "category": "functional" | "non_functional",
      "source_quote": "<exact words from FOCUS>",
      "language": "de" | "en",
      "certainty": "explicit" | "implied"
    }
  ]
}

If nothing applies, return {"requirements": []}.
"""

EXISTING_TAIL = 10
CONTEXT_TAIL = 3


def _format_utterance(u: Utterance) -> str:
    minutes = int(u.start_s // 60)
    secs = u.start_s - minutes * 60
    ts = f"{minutes:02d}:{secs:04.1f}"
    return f"[{ts}][{u.lang.upper()}] {u.text.strip()}"


def build_messages(
    *,
    focus: Utterance,
    context: list[Utterance],
    existing_texts: list[str],
) -> list[dict]:
    """Build the chat messages for the LLM extractor.

    - `focus`: the new utterance the LLM should extract from.
    - `context`: prior utterances (read-only context for resolving references).
    - `existing_texts`: already-extracted texts; truncated to the last EXISTING_TAIL.
    """
    parts: list[str] = []

    existing_tail = existing_texts[-EXISTING_TAIL:]
    if existing_tail:
        parts.append("EXISTING (do not duplicate):")
        parts.extend(f"- {t}" for t in existing_tail)
        parts.append("")

    context_tail = context[-CONTEXT_TAIL:]
    if context_tail:
        parts.append("CONTEXT (read-only, do not extract from this):")
        parts.extend(_format_utterance(u) for u in context_tail)
        parts.append("")

    parts.append("FOCUS (extract only from this):")
    parts.append(_format_utterance(focus))

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]
```

- [ ] **Step 3.2: Rewrite `backend/tests/test_extractor_prompt.py`**

Read the existing file first to preserve style. Replace its body with:

```python
from backend.extractor_prompt import SYSTEM_PROMPT, build_messages
from backend.sentence_buffer import Utterance


def _u(text: str, start: float = 0.0, end: float = 2.0, lang: str = "en") -> Utterance:
    return Utterance(text=text, start_s=start, end_s=end, lang=lang, segment_ids=["s1"])


def test_system_prompt_mentions_certainty_and_few_shot():
    assert "certainty" in SYSTEM_PROMPT
    assert "explicit" in SYSTEM_PROMPT
    assert "implied" in SYSTEM_PROMPT
    # Few-shot anchors
    assert "product requirements" in SYSTEM_PROMPT
    assert "must show monthly revenue" in SYSTEM_PROMPT


def test_system_prompt_does_not_mention_confidence():
    assert "confidence" not in SYSTEM_PROMPT.lower()


def test_build_messages_includes_focus_and_context():
    msgs = build_messages(
        focus=_u("The dashboard must show revenue.", 10.0, 13.0),
        context=[_u("We're building a CRM.", 0.0, 3.0)],
        existing_texts=[],
    )
    user = msgs[1]["content"]
    assert "FOCUS" in user
    assert "CONTEXT" in user
    assert "The dashboard must show revenue." in user
    assert "We're building a CRM." in user


def test_build_messages_truncates_existing_to_tail():
    many = [f"req {i}" for i in range(20)]
    msgs = build_messages(focus=_u("focus."), context=[], existing_texts=many)
    user = msgs[1]["content"]
    assert "req 19" in user
    assert "req 9" not in user  # only last 10 included


def test_build_messages_omits_context_block_if_empty():
    msgs = build_messages(focus=_u("focus."), context=[], existing_texts=[])
    user = msgs[1]["content"]
    assert "CONTEXT" not in user
    assert "FOCUS" in user
```

- [ ] **Step 3.3: Run prompt tests**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_prompt.py -v`
Expected: 5 passed.

- [ ] **Step 3.4: Commit**

```bash
git add backend/extractor_prompt.py backend/tests/test_extractor_prompt.py
git commit -m "feat(extractor): rewrite prompt with FOCUS+CONTEXT, few-shot, certainty"
```

---

## Task 4: Filter rewrite — new gates (length / verb / quote / dedupe / schema)

**Files:**
- Rewrite: `backend/extractor_filter.py`
- Rewrite: `backend/tests/test_extractor_filter.py`

- [ ] **Step 4.1: Replace `backend/extractor_filter.py`**

```python
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

GateName = Literal["is_requirement", "length", "verb", "source_quote", "dedupe", "schema"]


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
    min_text_len: int = field(default_factory=lambda: _env_int("EXTRACTOR_MIN_TEXT_LEN", 40))
    verb_gate: bool = field(default_factory=lambda: _env_bool("EXTRACTOR_VERB_GATE", True))
    quote_match_ratio: float = field(default_factory=lambda: _env_float("EXTRACTOR_QUOTE_MATCH_RATIO", 0.75))
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
    # German modal
    r"\bmuss\b", r"\bsoll\b", r"\bsollte\b", r"\bwird\b", r"\bbraucht\b",
    # German intent
    r"\bbrauchen\b", r"\bwollen\b", r"\bhinzufügen\b",
    r"\bzeigen\b", r"\bunterstützen\b",
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
    return SequenceMatcher(None, nq, ns).ratio() >= ratio


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
        # Gate 1
        if not c.get("is_requirement", False):
            dropped.append(DroppedCandidate(
                gate="is_requirement", reason=str(c.get("reasoning", "")), candidate=c,
            ))
            continue

        text = str(c.get("text", "")).strip()

        # Gate 2: length
        if len(text) < cfg.min_text_len:
            dropped.append(DroppedCandidate(
                gate="length", reason=f"{len(text)} < {cfg.min_text_len}", candidate=c,
            ))
            continue

        # Gate 3: verb
        if cfg.verb_gate and not _contains_verb(text):
            dropped.append(DroppedCandidate(
                gate="verb", reason="no modal/intent verb", candidate=c,
            ))
            continue

        # Gate 4: source_quote (always on)
        quote = str(c.get("source_quote", ""))
        if not _matches_focus(quote, focus, cfg.quote_match_ratio):
            dropped.append(DroppedCandidate(
                gate="source_quote", reason="quote not in focus", candidate=c,
            ))
            continue

        # Gate 5: fuzzy dedupe
        if _is_near_duplicate(text, existing_texts, cfg.dedupe_ratio):
            dropped.append(DroppedCandidate(
                gate="dedupe", reason="near-duplicate of existing", candidate=c,
            ))
            continue

        # Gate 6: schema sanity
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
```

- [ ] **Step 4.2: Rewrite `backend/tests/test_extractor_filter.py`**

```python
from backend.extractor_filter import FilterConfig, filter_candidates
from backend.sentence_buffer import Utterance


GOOD_TEXT = "The dashboard must show monthly revenue for all sales regions."
GOOD_QUOTE = "The dashboard must show monthly revenue for all sales regions."

FOCUS = Utterance(
    text=GOOD_QUOTE,
    start_s=0.0,
    end_s=3.0,
    lang="en",
    segment_ids=["s1"],
)
CFG = FilterConfig()


def _cand(**overrides) -> dict:
    base = {
        "is_requirement": True,
        "reasoning": "modal verb 'must' + complete clause",
        "text": GOOD_TEXT,
        "category": "functional",
        "source_quote": GOOD_QUOTE,
        "language": "en",
        "certainty": "explicit",
    }
    base.update(overrides)
    return base


def test_clean_candidate_passes():
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1
    assert out.dropped == []


def test_is_requirement_false_drops():
    out = filter_candidates([_cand(is_requirement=False)], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "is_requirement"


def test_length_gate_drops_short_fragments():
    short = _cand(text="product requirements", source_quote="product requirements")
    out = filter_candidates([short], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "length"


def test_length_gate_tunable_via_env():
    relaxed = FilterConfig(min_text_len=10)
    short = _cand(text="must show X.", source_quote="must show X.")
    short_focus = Utterance(text="must show X.", start_s=0.0, end_s=1.0, lang="en", segment_ids=["s1"])
    out = filter_candidates([short], focus=short_focus, existing_texts=[], cfg=relaxed)
    assert len(out.kept) == 1


def test_verb_gate_drops_text_without_modal_or_intent_verb():
    nv = _cand(
        text="The product roadmap discussion from yesterday's meeting was useful.",
        source_quote=GOOD_QUOTE,
    )
    out = filter_candidates([nv], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "verb"


def test_verb_gate_accepts_german_modal():
    de_focus = Utterance(
        text="Das Dashboard muss monatliche Einnahmen anzeigen.",
        start_s=0.0, end_s=3.0, lang="de", segment_ids=["s1"],
    )
    de = _cand(
        text="Das Dashboard muss monatliche Einnahmen anzeigen.",
        source_quote="Das Dashboard muss monatliche Einnahmen anzeigen.",
        language="de",
    )
    out = filter_candidates([de], focus=de_focus, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1


def test_verb_gate_can_be_disabled():
    cfg = FilterConfig(verb_gate=False)
    nv = _cand(
        text="The product roadmap discussion from yesterday's meeting was useful.",
    )
    out = filter_candidates([nv], focus=FOCUS, existing_texts=[], cfg=cfg)
    assert len(out.kept) == 1


def test_source_quote_must_match_focus():
    out = filter_candidates(
        [_cand(source_quote="This sentence is nowhere in the focus utterance.")],
        focus=FOCUS, existing_texts=[], cfg=CFG,
    )
    assert out.dropped[0].gate == "source_quote"


def test_fuzzy_dedupe_drops_near_duplicate():
    existing = ["The dashboard must show monthly revenue for sales regions."]
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=existing, cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "dedupe"


def test_fuzzy_dedupe_threshold_tunable():
    cfg = FilterConfig(dedupe_ratio=0.99)  # very strict — near-dupes pass
    existing = ["The dashboard must show monthly revenue for sales regions."]
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=existing, cfg=cfg)
    assert len(out.kept) == 1


def test_schema_invalid_certainty_drops():
    out = filter_candidates([_cand(certainty="probably")], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "schema"


def test_schema_invalid_category_drops():
    out = filter_candidates([_cand(category="ux")], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "schema"


def test_internal_fields_stripped_on_survivor():
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert "is_requirement" not in out.kept[0]
    assert "reasoning" not in out.kept[0]
    assert out.kept[0]["certainty"] == "explicit"
```

- [ ] **Step 4.3: Run filter tests**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_filter.py -v`
Expected: 13 passed.

- [ ] **Step 4.4: Commit**

```bash
git add backend/extractor_filter.py backend/tests/test_extractor_filter.py
git commit -m "feat(extractor): new filter gates (length, verb, fuzzy dedupe, certainty)"
```

---

## Task 5: ExtractorWorker rewrite — event-driven, FOCUS+CONTEXT

**Files:**
- Rewrite: `backend/extractor.py`
- Rewrite: `backend/tests/test_extractor.py`

- [ ] **Step 5.1: Replace `backend/extractor.py`**

```python
"""Event-driven worker that extracts requirements from utterances.

Consumes Utterances from a SentenceBuffer's queue. For each utterance, builds
a FOCUS+CONTEXT prompt, calls the LLM, filters candidates, and broadcasts
surviving Insights.

Skip-if-busy: if an LLM call is in flight when a new utterance arrives, the
new one is dropped (fresh signals matter more than catching every utterance).
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.extractor_filter import FilterConfig, filter_candidates
from backend.extractor_prompt import CONTEXT_TAIL, build_messages
from backend.insights import Insight
from backend.ollama_client import OllamaClient
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import SessionState


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractorWorker:
    def __init__(
        self,
        *,
        state: SessionState,
        hub: Any,
        client: OllamaClient,
        model: str,
        buffer: SentenceBuffer,
    ) -> None:
        self._state = state
        self._hub = hub
        self._client = client
        self._model = model
        self._buffer = buffer
        self._cfg = FilterConfig()
        self._in_flight = False
        self._counter = 0
        self._task: asyncio.Task | None = None
        self._context: deque[Utterance] = deque(maxlen=CONTEXT_TAIL)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                u = await self._buffer.queue.get()
                await self._handle(u)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[extractor] error: {exc}", file=sys.stderr)

    async def _handle(self, focus: Utterance) -> None:
        if self._state.recording_state != "recording":
            # Still update context so a resumed session has continuity.
            self._context.append(focus)
            return
        if self._in_flight:
            print("[extractor] skip-if-busy: dropping utterance", file=sys.stderr)
            self._context.append(focus)
            return

        self._in_flight = True
        try:
            existing_texts = [
                ins.text for ins in self._state.insights if ins.status != "declined"
            ][-10:]
            messages = build_messages(
                focus=focus,
                context=list(self._context),
                existing_texts=existing_texts,
            )
            try:
                raw = await self._client.chat(messages=messages, model=self._model)
            except httpx.HTTPError as exc:
                await self._hub.broadcast({
                    "type": "ai_status",
                    "state": "offline",
                    "model": self._model,
                    "error": str(exc),
                })
                return

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[extractor] non-json reply: {exc}; raw={raw[:200]!r}", file=sys.stderr)
                return

            candidates = data.get("requirements", []) or []
            if not isinstance(candidates, list):
                return

            result = filter_candidates(
                candidates,
                focus=focus,
                existing_texts=existing_texts,
                cfg=self._cfg,
            )

            for d in result.dropped:
                print(f"[extractor] dropped ({d.gate}): {d.reason}", file=sys.stderr)

            for cand in result.kept:
                self._counter += 1
                ins = Insight(
                    id=f"ins-{self._counter:03d}",
                    session_id=self._state.session_id or "sess-unknown",
                    category=cand["category"],
                    certainty=cand["certainty"],
                    text=cand["text"],
                    original_text=cand["text"],
                    source_quote=str(cand.get("source_quote", "")),
                    language=str(cand.get("language", "en")),
                    status="pending",
                    created_at_iso=_iso_now(),
                )
                self._state.insights.append(ins)
                await self._hub.broadcast({"type": "insight", "insight": _insight_to_dict(ins)})

            await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
        finally:
            self._in_flight = False
            self._context.append(focus)


def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "certainty": ins.certainty,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }
```

- [ ] **Step 5.2: Rewrite `backend/tests/test_extractor.py`**

Read the existing file first to see any fixtures it uses. Then replace its body with:

```python
import asyncio
import json
import pytest

from backend.extractor import ExtractorWorker
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import SessionState


class StubHub:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def broadcast(self, msg: dict) -> None:
        self.messages.append(msg)


class StubClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, *, messages, model):
        self.calls.append({"messages": messages, "model": model})
        if not self._responses:
            return json.dumps({"requirements": []})
        return self._responses.pop(0)


def _utt(text: str, start: float = 0.0, end: float = 3.0, lang: str = "en") -> Utterance:
    return Utterance(text=text, start_s=start, end_s=end, lang=lang, segment_ids=["s1"])


def _good_candidate(text: str) -> dict:
    return {
        "is_requirement": True,
        "reasoning": "modal + clause",
        "text": text,
        "category": "functional",
        "source_quote": text,
        "language": "en",
        "certainty": "explicit",
    }


@pytest.mark.asyncio
async def test_worker_processes_utterance_and_broadcasts_insight():
    state = SessionState()
    state.recording_state = "recording"
    state.session_id = "sess-x"
    hub = StubHub()
    text = "The dashboard must show monthly revenue for all regions."
    client = StubClient([json.dumps({"requirements": [_good_candidate(text)]})])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt(text))
        # Give the worker time to consume + process.
        await asyncio.sleep(0.05)
        assert any(m["type"] == "insight" for m in hub.messages)
        ins_msg = next(m for m in hub.messages if m["type"] == "insight")
        assert ins_msg["insight"]["certainty"] == "explicit"
        assert "confidence" not in ins_msg["insight"]
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_no_op_when_not_recording():
    state = SessionState()
    state.recording_state = "idle"
    hub = StubHub()
    client = StubClient([json.dumps({"requirements": []})])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt("anything."))
        await asyncio.sleep(0.05)
        assert client.calls == []  # LLM not called
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_passes_context_window():
    state = SessionState()
    state.recording_state = "recording"
    state.session_id = "sess-x"
    hub = StubHub()
    client = StubClient([
        json.dumps({"requirements": []}),
        json.dumps({"requirements": []}),
    ])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt("We're building a CRM.", 0.0, 2.0))
        await asyncio.sleep(0.05)
        await buffer.queue.put(_utt("It must support Salesforce sync.", 2.0, 5.0))
        await asyncio.sleep(0.05)
        # Second call should include first utterance in CONTEXT.
        assert len(client.calls) == 2
        second_user_msg = client.calls[1]["messages"][1]["content"]
        assert "CONTEXT" in second_user_msg
        assert "We're building a CRM." in second_user_msg
    finally:
        await worker.stop()
```

- [ ] **Step 5.3: Run extractor tests**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor.py -v`
Expected: 3 passed.

- [ ] **Step 5.4: Commit**

```bash
git add backend/extractor.py backend/tests/test_extractor.py
git commit -m "feat(extractor): event-driven worker with FOCUS+CONTEXT prompt"
```

---

## Task 6: Server wiring — buffer in lifespan, `_insight_to_dict`, segment ingest

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/tests/test_control.py` (if it references confidence)

- [ ] **Step 6.1: Read the current `backend/server.py`**

Use `Read` to confirm exact line context before editing.

- [ ] **Step 6.2: Update imports**

In the import block at the top of `backend/server.py`, add:

```python
from backend.sentence_buffer import SentenceBuffer
```

- [ ] **Step 6.3: Update `lifespan`**

Find the block that constructs `app.state.extractor` and replace it with:

```python
    app.state.sentence_buffer = SentenceBuffer()
    app.state.extractor = ExtractorWorker(
        state=app.state.session,
        hub=app.state.hub,
        client=app.state.ollama_client,
        model=model,
        buffer=app.state.sentence_buffer,
    )
    app.state.extractor.start()
```

- [ ] **Step 6.4: Feed segments into the buffer**

In `post_segment`, after `app.state.session.add_segment(seg)`, add:

```python
    await app.state.sentence_buffer.add(seg)
```

So the route becomes:

```python
@app.post("/segments", status_code=202)
async def post_segment(payload: SegmentIn) -> dict:
    seg = Segment(
        id=payload.id,
        session_id=payload.session_id,
        text=payload.text,
        start_s=payload.start_s,
        end_s=payload.end_s,
        lang=payload.lang,
    )
    app.state.session.add_segment(seg)
    await app.state.sentence_buffer.add(seg)
    await app.state.hub.broadcast({"type": "segment", "segment": _segment_to_dict(seg)})
    asyncio.create_task(_deliver_and_report(seg))
    return {"accepted": True}
```

- [ ] **Step 6.5: Reset buffer on new session**

In `control_start`, where `app.state.session.reset(...)` is called, add right after it:

```python
        app.state.sentence_buffer.reset()
```

The `if not resuming_from_paused:` block should look like:

```python
    if not resuming_from_paused:
        _archive_current_session(app)
        app.state.session.reset(session_id=_new_session_id())
        app.state.sentence_buffer.reset()
```

- [ ] **Step 6.6: Update `_insight_to_dict`**

Replace the module-level `_insight_to_dict` in `backend/server.py` with:

```python
def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "certainty": ins.certainty,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }
```

- [ ] **Step 6.7: Run the full backend test suite**

Run: `PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q`
Expected: all pass. If `test_control.py` or any other test still references `.confidence`, fix it: replace with `certainty="explicit"` (or `"implied"` where the test name implies inference). If a test mocks `Insight(...)` constructor positional args, update to keyword args matching the new shape.

- [ ] **Step 6.8: Commit**

```bash
git add backend/server.py backend/tests
git commit -m "feat(server): wire SentenceBuffer to ExtractorWorker; drop confidence from API"
```

---

## Task 7: UI — certainty badge in `InsightCard`

**Files:**
- Modify: `ui/src/components/InsightCard.tsx`

- [ ] **Step 7.1: Replace the confidence percentage with a certainty badge**

In `ui/src/components/InsightCard.tsx`, near the top below `CATEGORY_CLASS`, add:

```ts
const CERTAINTY_LABEL = {
  explicit: "Explicit",
  implied: "Implied",
} as const;

const CERTAINTY_CLASS = {
  explicit: "bg-neon-cyan/15 text-neon-cyan border-neon-cyan/40",
  implied: "bg-neon-amber/15 text-neon-amber border-neon-amber/40",
} as const;
```

Then replace the header span that shows `{(insight.confidence * 100).toFixed(0)}%` with:

```tsx
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border ml-auto",
            CERTAINTY_CLASS[insight.certainty],
          )}
        >
          {CERTAINTY_LABEL[insight.certainty]}
        </span>
```

The header block should end up looking like:

```tsx
      <div className="flex items-center justify-between gap-2 mb-2">
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border",
            CATEGORY_CLASS[insight.category],
          )}
        >
          {CATEGORY_LABEL[insight.category]}
        </span>
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border ml-auto",
            CERTAINTY_CLASS[insight.certainty],
          )}
        >
          {CERTAINTY_LABEL[insight.certainty]}
        </span>
      </div>
```

- [ ] **Step 7.2: Type-check the UI**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors. If `confidence` is still referenced elsewhere in `ui/src/**`, fix those usages (most likely none — `useSessionWs.ts` is field-agnostic). Run `grep -rn confidence ui/src` to confirm zero matches.

- [ ] **Step 7.3: Commit**

```bash
git add ui/src/components/InsightCard.tsx
git commit -m "feat(ui): replace confidence % with explicit/implied certainty badge"
```

---

## Task 8: README updates + manual acceptance

**Files:**
- Modify: `README.md`

- [ ] **Step 8.1: Update the tunable env vars table**

In the `## Running the dashboard` section, replace the **Tunable env vars** table with:

```markdown
**Tunable env vars:**

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `phi3` | Local LLM for AI insights. Try `mistral`, `llama3.1`, `qwen2.5`. |
| `OLLAMA_URL` | `http://localhost:11434` | Override if Ollama runs elsewhere. |
| `BUFFER_MAX_SILENCE_S` | `1.5` | Silence gap (s) that flushes the sentence buffer. |
| `BUFFER_MAX_DURATION_S` | `20.0` | Hard buffer-flush duration (s). |
| `EXTRACTOR_MIN_TEXT_LEN` | `40` | Minimum chars for an extracted requirement. |
| `EXTRACTOR_VERB_GATE` | `true` | Require a modal/intent verb in the extracted text. |
| `EXTRACTOR_QUOTE_MATCH_RATIO` | `0.75` | Fuzziness for matching `source_quote` against the focus utterance. |
| `EXTRACTOR_DEDUPE_RATIO` | `0.85` | Fuzzy similarity above which a candidate is treated as a duplicate. |
| `DOINGS_ENDPOINT` | `https://staging.doings.de/stt` | Per-segment delivery target. |
```

- [ ] **Step 8.2: Update the troubleshooting row about insight counts**

Replace the existing row:

```
| Insights are too few / too many | Tune `EXTRACTOR_CONFIDENCE_FLOOR` (default `0.6`). ... |
```

with:

```
| Insights are too few / too many | Tune `EXTRACTOR_MIN_TEXT_LEN` (default `40`) or `EXTRACTOR_VERB_GATE` (default `true`). Lower min length or disable the verb gate → more pass through. Restart backend after env changes. |
```

- [ ] **Step 8.3: Run the full backend test suite + UI type check**

Run in parallel:
```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q
cd ui && npx tsc --noEmit
```

Expected: backend all pass, UI 0 errors.

- [ ] **Step 8.4: Manual acceptance**

Run all four terminals from `README.md` Quick start. With the dashboard open at http://localhost:5173:

1. Click ▶ Start.
2. Read this monologue aloud (slowly, with sentence breaks):

   > "Hi team. We're building a new sales CRM. The dashboard must show monthly revenue. It needs to support German language input. Sales reports should export to CSV. That's all for now."

3. Verify in the AI Insights panel:
   - **Three cards appear**, one per requirement sentence.
   - Each card shows a cyan "Explicit" badge (none should be "Implied" because each sentence has a modal/intent verb verbatim).
   - **No fragment cards** ("revenue", "for now", "Hi team", etc.).
   - **No duplicate cards** — speaking the same sentence twice should not produce two cards (fuzzy dedupe).
4. Click ■ Stop.

If any of those fail, do NOT commit; report which gate is misbehaving (check backend stderr — every drop is logged with `[extractor] dropped (<gate>): <reason>`).

- [ ] **Step 8.5: Commit**

```bash
git add README.md
git commit -m "docs: README env vars for sentence buffer + new filter gates"
```

---

## Spec coverage check

| Spec section | Task(s) |
|---|---|
| Layer 1: SentenceBuffer (`sentence_buffer.py`) | Task 1 |
| Layer 2: Event-driven extractor | Task 5 |
| Layer 3a: Prompt rewrite + few-shot | Task 3 |
| Layer 3b: Filter gates (length, verb, quote, dedupe, schema) | Task 4 |
| Schema change `confidence` → `certainty` | Task 2 |
| UI badge update | Task 7 |
| Env vars wired and documented | Tasks 1, 4 (code), 8 (docs) |
| Manual acceptance against the slop demo | Task 8 |
| Future work (Step 4) | Not in scope — captured in spec |
