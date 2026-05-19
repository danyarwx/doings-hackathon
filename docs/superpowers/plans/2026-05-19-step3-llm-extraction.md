# Step 3 — Local LLM Requirements Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local LLM (default `phi3` via Ollama) reads a rolling 30-second transcript every 5 seconds, proposes software requirements, and renders them as Approve / Edit / Decline cards in the AI Insights panel.

**Architecture:** New `ExtractorWorker` async task in the FastAPI lifespan polls Ollama on a timer, runs a 5-gate quality filter on the JSON output (is_requirement flag, confidence floor, source-quote validation, exact-text dedup, schema sanity), appends survivors to `SessionState.insights`, and broadcasts them over the existing WebSocket. UI hook handles three new WS message types; `InsightCard` gains Edit (inline textarea) and Decline.

**Tech Stack:** Python 3.10+ · FastAPI · httpx (async) · pydantic · pytest · respx · React 18 · TypeScript · Tailwind. Ollama runs locally on `localhost:11434`.

**Spec:** [docs/superpowers/specs/2026-05-19-step3-llm-extraction-design.md](../specs/2026-05-19-step3-llm-extraction-design.md)

---

## File Structure

### Backend (new + modified)

| File | Responsibility |
|---|---|
| `backend/insights.py` | `Insight` dataclass + `InsightStatus` literal. Pure data; no logic. |
| `backend/ollama_client.py` | Thin async wrapper around Ollama `POST /api/chat` and `GET /api/tags`. Returns `"ok" | "no_model" | "offline"` from `health()`. |
| `backend/extractor_prompt.py` | `build_messages(window, existing, …)` returns chat messages. Isolated for prompt iteration. |
| `backend/extractor_filter.py` | 5-gate quality filter — pure functions. Stdlib only (`difflib.SequenceMatcher`). |
| `backend/extractor.py` | `ExtractorWorker`: timer loop, window builder, glue between client + prompt + filter + broadcast. |
| `backend/state.py` | `SessionState` gains `insights: list[Insight]`; `reset()` clears it. |
| `backend/server.py` | New routes (`/insights`, `/insights/{id}/approve|decline|edit`, `/ai/status`). Start `ExtractorWorker` in lifespan. |
| `backend/tests/test_ollama_client.py` | respx mocks for chat success / timeout / connection error / 404 |
| `backend/tests/test_extractor_filter.py` | Each filter gate, with realistic candidate dicts |
| `backend/tests/test_extractor.py` | Worker behavior with stubbed `OllamaClient` |
| `backend/tests/test_insights_api.py` | Endpoint tests (approve / decline / edit / 404) |

### UI (modified)

| File | Change |
|---|---|
| `ui/src/lib/types.ts` | Narrow `Insight.category` to `functional|non_functional`; drop `InsightType` union; drop `rejected` status; add `original_text`; add `AiStatus` type; extend `WsMessage`. |
| `ui/src/lib/api.ts` | `approveInsight(id)`, `declineInsight(id)`, `editInsight(id, text)` |
| `ui/src/lib/useSessionWs.ts` | Handle `insight`, `insight_update`, `ai_status` messages. Track `insights: Map`, `aiStatus`. Reset on session_id change. |
| `ui/src/components/InsightCard.tsx` | Replace Reject → Decline. Add Edit (inline textarea). Wire to API. |
| `ui/src/components/InsightsPanel.tsx` | Source from hook (not props). Status badge in header. |
| `ui/src/App.tsx` | Drop `insights` prop on InsightsPanel (now hook-sourced). |

---

### Task 1: `Insight` dataclass + status type

**Files:**
- Create: `/Users/danila/Documents/doings/backend/insights.py`
- Test: `/Users/danila/Documents/doings/backend/tests/test_insights_model.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_insights_model.py
from backend.insights import Insight


def test_insight_minimal_fields():
    ins = Insight(
        id="ins-001",
        session_id="sess-x",
        category="functional",
        text="The system must handle 500 concurrent users.",
        original_text="The system must handle 500 concurrent users.",
        source_quote="The system must handle 500 concurrent users.",
        language="en",
        confidence=0.8,
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    assert ins.status == "pending"
    assert ins.category == "functional"


def test_insight_is_frozen():
    ins = Insight(
        id="ins-001",
        session_id="sess-x",
        category="functional",
        text="x",
        original_text="x",
        source_quote="x",
        language="en",
        confidence=0.8,
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    import dataclasses
    try:
        ins.status = "approved"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Insight should be frozen")
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /Users/danila/Documents/doings
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_insights_model.py -v
```

Expected: FAIL — `backend.insights` not found.

- [ ] **Step 3: Implement `backend/insights.py`**

```python
"""Insight model (LLM-extracted requirement candidate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InsightStatus = Literal["pending", "approved", "declined"]
InsightCategory = Literal["functional", "non_functional"]


@dataclass(frozen=True)
class Insight:
    id: str
    session_id: str
    category: InsightCategory
    text: str
    original_text: str
    source_quote: str
    language: str
    confidence: float
    status: InsightStatus
    created_at_iso: str
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_insights_model.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/insights.py backend/tests/test_insights_model.py
git commit -m "backend: Insight dataclass"
```

---

### Task 2: SessionState gains insights list

**Files:**
- Modify: `/Users/danila/Documents/doings/backend/state.py`
- Modify: `/Users/danila/Documents/doings/backend/tests/test_state.py`

- [ ] **Step 1: Append a test to `backend/tests/test_state.py`**

Open the existing file and append:

```python
def test_reset_clears_insights_too():
    from backend.insights import Insight
    state = SessionState()
    ins = Insight(
        id="ins-001",
        session_id="s1",
        category="functional",
        text="x",
        original_text="x",
        source_quote="x",
        language="en",
        confidence=0.8,
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    state.insights.append(ins)
    state.reset(session_id="s2")
    assert state.insights == []


def test_initial_state_has_empty_insights():
    state = SessionState()
    assert state.insights == []
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_state.py -v
```

Expected: 2 new tests FAIL (no `insights` attribute).

- [ ] **Step 3: Modify `backend/state.py`**

Find the existing `SessionState` dataclass. Update it:

```python
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
        self.session_id = session_id
        self.recording_state = "idle"
```

- [ ] **Step 4: Run all backend tests, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -v
```

Expected: all previous tests still pass + 2 new state tests = at least 20 total.

- [ ] **Step 5: Commit**

```bash
git add backend/state.py backend/tests/test_state.py
git commit -m "backend: SessionState.insights list (cleared on reset)"
```

---

### Task 3: OllamaClient

**Files:**
- Create: `/Users/danila/Documents/doings/backend/ollama_client.py`
- Test: `/Users/danila/Documents/doings/backend/tests/test_ollama_client.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_ollama_client.py
import httpx
import pytest
import respx

from backend.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_chat_returns_assistant_content():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.post("/api/chat").respond(
            200,
            json={"message": {"role": "assistant", "content": '{"requirements": []}'}},
        )
        client = OllamaClient()
        out = await client.chat(messages=[{"role": "user", "content": "x"}], model="phi3")
    assert out == '{"requirements": []}'


@pytest.mark.asyncio
async def test_chat_timeout_raises():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.post("/api/chat").mock(side_effect=httpx.TimeoutException("slow"))
        client = OllamaClient()
        with pytest.raises(httpx.TimeoutException):
            await client.chat(
                messages=[{"role": "user", "content": "x"}],
                model="phi3",
                timeout_s=0.1,
            )


@pytest.mark.asyncio
async def test_health_ok():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").respond(
            200, json={"models": [{"name": "phi3:latest"}, {"name": "mistral:latest"}]}
        )
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "ok"


@pytest.mark.asyncio
async def test_health_no_model():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").respond(200, json={"models": [{"name": "llama3:latest"}]})
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "no_model"


@pytest.mark.asyncio
async def test_health_offline():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").mock(side_effect=httpx.ConnectError("nope"))
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "offline"
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_ollama_client.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `backend/ollama_client.py`**

```python
"""Async wrapper around Ollama's HTTP API."""

from __future__ import annotations

from typing import Literal

import httpx

HealthStatus = Literal["ok", "no_model", "offline"]


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        format: str | None = "json",
        temperature: float = 0.2,
        timeout_s: float = 30.0,
    ) -> str:
        """Call POST /api/chat and return the assistant's content string."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format is not None:
            payload["format"] = format
        async with httpx.AsyncClient(timeout=timeout_s) as http:
            r = await http.post(f"{self._base}/api/chat", json=payload)
            r.raise_for_status()
            body = r.json()
        return body["message"]["content"]

    async def health(self, *, model: str, timeout_s: float = 2.0) -> HealthStatus:
        """Probe Ollama and check the named model is installed."""
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                r = await http.get(f"{self._base}/api/tags")
            if r.status_code != 200:
                return "offline"
            installed = [m.get("name", "") for m in r.json().get("models", [])]
            # Ollama stores names as "phi3:latest"; compare by stem.
            stems = {n.split(":", 1)[0] for n in installed}
            return "ok" if model in stems else "no_model"
        except httpx.HTTPError:
            return "offline"
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_ollama_client.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/ollama_client.py backend/tests/test_ollama_client.py
git commit -m "backend: OllamaClient (chat + health)"
```

---

### Task 4: Extractor prompt template

**Files:**
- Create: `/Users/danila/Documents/doings/backend/extractor_prompt.py`
- Test: `/Users/danila/Documents/doings/backend/tests/test_extractor_prompt.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_extractor_prompt.py
from backend.extractor_prompt import build_messages
from backend.state import Segment


def _seg(text: str, start: float = 0.0, end: float = 1.0, lang: str = "en") -> Segment:
    return Segment(id="seg-001", session_id="s1", text=text, start_s=start, end_s=end, lang=lang)


def test_messages_have_system_and_user():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_prompt_includes_schema_keys():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    sys_text = msgs[0]["content"]
    for key in ("is_requirement", "reasoning", "text", "category", "source_quote", "language", "confidence"):
        assert key in sys_text, f"missing {key} in system prompt"


def test_user_includes_existing_and_window():
    msgs = build_messages(
        window=[_seg("Das System muss schnell sein.", lang="de", end=12.4)],
        existing_texts=["Auth uses OAuth"],
    )
    user_text = msgs[1]["content"]
    assert "Auth uses OAuth" in user_text
    assert "Das System muss schnell sein." in user_text
    assert "[DE]" in user_text


def test_user_omits_existing_block_when_empty():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    user_text = msgs[1]["content"]
    assert "EXISTING" not in user_text or "do not duplicate" in user_text.lower()


def test_existing_is_truncated_to_last_10():
    msgs = build_messages(
        window=[_seg("hi")],
        existing_texts=[f"req {i}" for i in range(20)],
    )
    user_text = msgs[1]["content"]
    # Keeps the last 10 (req 10..19), drops the first 10
    assert "req 19" in user_text
    assert "req 10" in user_text
    assert "req 9" not in user_text
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_prompt.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `backend/extractor_prompt.py`**

```python
"""Prompt builder for the requirements-extractor LLM."""

from __future__ import annotations

from backend.state import Segment

SYSTEM_PROMPT = """You are a requirements extractor for engineering meetings. Output ONLY valid JSON that matches the schema below — no prose, no markdown.

A REQUIREMENT is a statement constraining what the system MUST, SHOULD, or HAS TO do. Hallmarks:
- Modal verb of obligation (must, shall, should, has to / muss, sollte, soll)
- Refers to system behavior, capability, performance, or a constraint
- Stated as a fact about the product, not as an opinion or aside

EXTRACT
- Functional requirements (what the system does)
- Non-functional requirements (performance, security, reliability, scalability, compliance, availability)

DO NOT EXTRACT
- Items already in the EXISTING list (you will receive them — do not repeat)
- Implementation decisions ("we'll use Postgres") unless they encode a real constraint
- Questions, opinions, side comments, agreements ("yeah", "ok", "great")
- Generic chatter, meta-talk about the meeting itself
- Things the speaker is hypothesizing or exploring, not committing to

Output the requirement text in the same language as the source quote (de stays de, en stays en).

For each candidate, INCLUDE an `is_requirement` boolean and a short `reasoning` (one sentence) — answer those FIRST inside your head before filling in `text`. If `is_requirement` is false, still include the entry so the filter can see your reasoning; the backend will drop it.

`source_quote` MUST be the exact words copied from the TRANSCRIPT WINDOW — no paraphrasing, no shortening. If you can't quote it exactly, set `is_requirement` to false.

`confidence` must reflect your real confidence (0.0–1.0). Use 0.5 if unsure. The backend will drop low-confidence items.

SCHEMA
{
  "requirements": [
    {
      "is_requirement": true | false,
      "reasoning": "<one sentence justifying the is_requirement decision>",
      "text": "<the requirement in the source language>",
      "category": "functional" | "non_functional",
      "source_quote": "<exact words from transcript>",
      "language": "de" | "en",
      "confidence": 0.0..1.0
    }
  ]
}

If nothing applies, return {"requirements": []}.
"""

EXISTING_TAIL = 10


def _format_segment(seg: Segment) -> str:
    minutes = int(seg.start_s // 60)
    secs = seg.start_s - minutes * 60
    ts = f"{minutes:02d}:{secs:04.1f}"
    return f"[{ts}][{seg.lang.upper()}] {seg.text.strip()}"


def build_messages(
    *,
    window: list[Segment],
    existing_texts: list[str],
) -> list[dict]:
    """Build the chat messages for the LLM extractor.

    - `window`: ordered segments from oldest to newest within the rolling window.
    - `existing_texts`: previously-extracted (non-declined) requirement texts; we
      truncate to the last `EXISTING_TAIL` to keep the prompt bounded.
    """
    existing_tail = existing_texts[-EXISTING_TAIL:]
    parts: list[str] = []
    if existing_tail:
        parts.append("EXISTING (do not duplicate):")
        parts.extend(f"- {t}" for t in existing_tail)
        parts.append("")
    parts.append("TRANSCRIPT WINDOW (oldest first):")
    parts.extend(_format_segment(s) for s in window)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_prompt.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractor_prompt.py backend/tests/test_extractor_prompt.py
git commit -m "backend: extractor prompt builder"
```

---

### Task 5: 5-gate quality filter

**Files:**
- Create: `/Users/danila/Documents/doings/backend/extractor_filter.py`
- Test: `/Users/danila/Documents/doings/backend/tests/test_extractor_filter.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_extractor_filter.py
from backend.extractor_filter import FilterConfig, FilterResult, filter_candidates
from backend.state import Segment


def _seg(text: str, lang: str = "en") -> Segment:
    return Segment(id="seg-001", session_id="s1", text=text, start_s=0.0, end_s=1.0, lang=lang)


WINDOW = [_seg("The system must handle 500 concurrent users."), _seg("Auth should use OAuth 2.0.")]
CFG = FilterConfig()


def _cand(**overrides) -> dict:
    base = {
        "is_requirement": True,
        "reasoning": "modal verb 'must' + system constraint",
        "text": "The system must handle 500 concurrent users.",
        "category": "non_functional",
        "source_quote": "The system must handle 500 concurrent users.",
        "language": "en",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_clean_candidate_passes():
    out = filter_candidates([_cand()], window=WINDOW, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1
    assert out.dropped == []


def test_gate1_is_requirement_false_drops():
    out = filter_candidates([_cand(is_requirement=False)], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "is_requirement"


def test_gate2_low_confidence_drops():
    out = filter_candidates([_cand(confidence=0.4)], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "confidence"


def test_gate2_confidence_floor_env_tunable():
    relaxed = FilterConfig(confidence_floor=0.3)
    out = filter_candidates([_cand(confidence=0.4)], window=WINDOW, existing_texts=[], cfg=relaxed)
    assert len(out.kept) == 1


def test_gate3_hallucinated_quote_drops():
    out = filter_candidates(
        [_cand(source_quote="This sentence is nowhere in the transcript at all.")],
        window=WINDOW,
        existing_texts=[],
        cfg=CFG,
    )
    assert out.kept == []
    assert out.dropped[0].gate == "source_quote"


def test_gate3_paraphrased_quote_close_enough_passes():
    # Minor punctuation diff is fine
    out = filter_candidates(
        [_cand(source_quote="the system must handle 500 concurrent users")],
        window=WINDOW,
        existing_texts=[],
        cfg=CFG,
    )
    assert len(out.kept) == 1


def test_gate3_can_be_disabled():
    relaxed = FilterConfig(require_source_quote=False)
    out = filter_candidates(
        [_cand(source_quote="anything goes")],
        window=WINDOW,
        existing_texts=[],
        cfg=relaxed,
    )
    assert len(out.kept) == 1


def test_gate4_exact_dedup_drops():
    out = filter_candidates(
        [_cand()],
        window=WINDOW,
        existing_texts=["The system must handle 500 concurrent users."],
        cfg=CFG,
    )
    assert out.kept == []
    assert out.dropped[0].gate == "dedup"


def test_gate4_dedup_case_insensitive():
    out = filter_candidates(
        [_cand()],
        window=WINDOW,
        existing_texts=["the SYSTEM must handle 500 concurrent users."],
        cfg=CFG,
    )
    assert out.kept == []


def test_gate5_invalid_category_drops():
    out = filter_candidates([_cand(category="bogus")], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "schema"


def test_gate5_empty_text_drops():
    out = filter_candidates([_cand(text="   ")], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "schema"


def test_filter_result_kept_loses_reasoning_and_is_requirement():
    out = filter_candidates([_cand()], window=WINDOW, existing_texts=[], cfg=CFG)
    kept = out.kept[0]
    assert "reasoning" not in kept
    assert "is_requirement" not in kept
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_filter.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `backend/extractor_filter.py`**

```python
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
        survivor["text"] = text  # normalized stripping
        kept.append(survivor)

    return FilterResult(kept=kept, dropped=dropped)
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor_filter.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractor_filter.py backend/tests/test_extractor_filter.py
git commit -m "backend: 5-gate quality filter for LLM candidates"
```

---

### Task 6: ExtractorWorker

**Files:**
- Create: `/Users/danila/Documents/doings/backend/extractor.py`
- Test: `/Users/danila/Documents/doings/backend/tests/test_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_extractor.py
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend.extractor import ExtractorWorker, build_window
from backend.insights import Insight
from backend.state import Segment, SessionState


def _seg(text: str, end: float, lang: str = "en") -> Segment:
    return Segment(
        id=f"seg-{int(end)}", session_id="s1", text=text, start_s=max(0.0, end - 1.0), end_s=end, lang=lang
    )


def test_build_window_keeps_recent():
    segs = [_seg(f"t{i}", end=float(i)) for i in range(60)]
    window = build_window(segs, window_s=30.0)
    # window spans last 30s ending at end_s=59
    assert window[-1].end_s == 59.0
    # earliest kept end_s should be >= 29
    assert window[0].end_s >= 29.0


def test_build_window_empty():
    assert build_window([], window_s=30.0) == []


@pytest.mark.asyncio
async def test_tick_skips_when_idle():
    state = SessionState()
    state.recording_state = "idle"
    client = AsyncMock()
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()
    client.chat.assert_not_called()


@pytest.mark.asyncio
async def test_tick_extracts_and_broadcasts():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("The system must handle 500 concurrent users.", end=5.0))

    client = AsyncMock()
    client.chat.return_value = json.dumps({
        "requirements": [{
            "is_requirement": True,
            "reasoning": "modal verb + system constraint",
            "text": "The system must handle 500 concurrent users.",
            "category": "non_functional",
            "source_quote": "The system must handle 500 concurrent users.",
            "language": "en",
            "confidence": 0.9,
        }]
    })
    hub = AsyncMock()

    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    assert len(state.insights) == 1
    assert state.insights[0].category == "non_functional"
    hub.broadcast.assert_called()
    # First broadcast should be an "insight" message
    first_call_args = hub.broadcast.call_args_list[0].args[0]
    assert first_call_args["type"] == "insight"


@pytest.mark.asyncio
async def test_tick_drops_low_confidence():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("The system must handle 500 users.", end=5.0))

    client = AsyncMock()
    client.chat.return_value = json.dumps({
        "requirements": [{
            "is_requirement": True,
            "reasoning": "not sure",
            "text": "The system must handle 500 users.",
            "category": "functional",
            "source_quote": "The system must handle 500 users.",
            "language": "en",
            "confidence": 0.3,
        }]
    })
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    assert state.insights == []


@pytest.mark.asyncio
async def test_tick_handles_invalid_json():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    client = AsyncMock()
    client.chat.return_value = "not even json"
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()  # must not raise

    assert state.insights == []


@pytest.mark.asyncio
async def test_tick_skips_when_inflight():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    async def slow_chat(*a, **kw):
        await asyncio.sleep(0.1)
        return json.dumps({"requirements": []})

    client = AsyncMock()
    client.chat.side_effect = slow_chat
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")

    # Fire two ticks back to back; the second should bail because _in_flight
    t1 = asyncio.create_task(w._tick_once())
    await asyncio.sleep(0.01)
    await w._tick_once()  # second call
    await t1

    assert client.chat.call_count == 1


@pytest.mark.asyncio
async def test_tick_broadcasts_ai_status_offline():
    import httpx
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    client = AsyncMock()
    client.chat.side_effect = httpx.ConnectError("nope")
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    calls = [c.args[0] for c in hub.broadcast.call_args_list]
    assert any(c.get("type") == "ai_status" and c.get("state") == "offline" for c in calls)
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `backend/extractor.py`**

```python
"""Async worker that extracts requirements from the rolling transcript window."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.extractor_filter import FilterConfig, filter_candidates
from backend.extractor_prompt import build_messages
from backend.insights import Insight
from backend.ollama_client import OllamaClient
from backend.state import Segment, SessionState

DEFAULT_TICK_S = 5.0
DEFAULT_WINDOW_S = 30.0


def build_window(segments: list[Segment], window_s: float) -> list[Segment]:
    if not segments:
        return []
    cutoff = max(0.0, segments[-1].end_s - window_s)
    return [s for s in segments if s.end_s >= cutoff]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractorWorker:
    def __init__(
        self,
        *,
        state: SessionState,
        hub: Any,  # has async broadcast(dict)
        client: OllamaClient,
        model: str,
        tick_s: float = DEFAULT_TICK_S,
        window_s: float = DEFAULT_WINDOW_S,
    ) -> None:
        self._state = state
        self._hub = hub
        self._client = client
        self._model = model
        self._tick_s = tick_s
        self._window_s = window_s
        self._cfg = FilterConfig()
        self._in_flight = False
        self._counter = 0
        self._task: asyncio.Task | None = None

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
            await asyncio.sleep(self._tick_s)
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[extractor] tick error: {exc}", file=sys.stderr)

    async def _tick_once(self) -> None:
        if self._state.recording_state != "recording":
            return
        if self._in_flight:
            return
        window = build_window(self._state.segments, self._window_s)
        if not window:
            return

        self._in_flight = True
        try:
            existing_texts = [
                ins.text for ins in self._state.insights if ins.status != "declined"
            ]
            messages = build_messages(window=window, existing_texts=existing_texts)
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
                window=window,
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
                    text=cand["text"],
                    original_text=cand["text"],
                    source_quote=str(cand.get("source_quote", "")),
                    language=str(cand.get("language", "en")),
                    confidence=float(cand.get("confidence", 0.0)),
                    status="pending",
                    created_at_iso=_iso_now(),
                )
                self._state.insights.append(ins)
                await self._hub.broadcast({"type": "insight", "insight": _insight_to_dict(ins)})

            # Successful chat call — mark AI as ok.
            await self._hub.broadcast({"type": "ai_status", "state": "ok", "model": self._model})
        finally:
            self._in_flight = False


def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "confidence": ins.confidence,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_extractor.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractor.py backend/tests/test_extractor.py
git commit -m "backend: ExtractorWorker (timer + filter + broadcast)"
```

---

### Task 7: Wire endpoints + worker lifecycle into server.py

**Files:**
- Modify: `/Users/danila/Documents/doings/backend/server.py`
- Create: `/Users/danila/Documents/doings/backend/tests/test_insights_api.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_insights_api.py
import time


def _post_seg(client, sid="seg-001", text="The system must handle 500 users.", lang="en"):
    return client.post(
        "/segments",
        json={
            "id": sid,
            "session_id": "sess-test",
            "text": text,
            "start_s": 0.0,
            "end_s": 1.0,
            "lang": lang,
        },
    )


def _seed_insight(app_module):
    """Append a stub Insight directly to session state for endpoint tests."""
    from backend.insights import Insight
    ins = Insight(
        id="ins-001",
        session_id="sess-seed",
        category="functional",
        text="The system must handle 500 users.",
        original_text="The system must handle 500 users.",
        source_quote="The system must handle 500 users.",
        language="en",
        confidence=0.9,
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    app_module.app.state.session.insights.append(ins)
    return ins


def test_get_insights_returns_list(client, app_module):
    _seed_insight(app_module)
    r = client.get("/insights")
    assert r.status_code == 200
    body = r.json()
    assert len(body["insights"]) == 1
    assert body["insights"][0]["id"] == "ins-001"


def test_approve_marks_status(client, app_module):
    _seed_insight(app_module)
    r = client.post("/insights/ins-001/approve")
    assert r.status_code == 200
    assert r.json()["insight"]["status"] == "approved"


def test_decline_marks_status(client, app_module):
    _seed_insight(app_module)
    r = client.post("/insights/ins-001/decline")
    assert r.status_code == 200
    assert r.json()["insight"]["status"] == "declined"


def test_edit_updates_text_and_keeps_pending(client, app_module):
    _seed_insight(app_module)
    r = client.post("/insights/ins-001/edit", json={"text": "Reworded requirement."})
    assert r.status_code == 200
    body = r.json()["insight"]
    assert body["text"] == "Reworded requirement."
    assert body["status"] == "pending"
    assert body["original_text"] == "The system must handle 500 users."


def test_endpoints_404_when_id_missing(client):
    r = client.post("/insights/ins-nope/approve")
    assert r.status_code == 404


def test_ai_status_endpoint(client):
    r = client.get("/ai/status")
    # Without ollama running locally, expect offline (in test env).
    assert r.status_code == 200
    assert r.json()["state"] in ("ok", "no_model", "offline")
    assert "model" in r.json()
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_insights_api.py -v
```

Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Modify `backend/server.py`**

Open the file. After the existing imports, add:

```python
from backend.extractor import ExtractorWorker
from backend.insights import Insight
from backend.ollama_client import OllamaClient
```

Add a module-level constant near `DEFAULT_ENDPOINT`:

```python
DEFAULT_MODEL = "phi3"
```

Update the `lifespan` function so it spins up `OllamaClient` + `ExtractorWorker`. Replace the existing body of `lifespan`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = SessionState()
    app.state.hub = Hub()
    app.state.endpoint = os.getenv("DOINGS_ENDPOINT", DEFAULT_ENDPOINT)
    app.state.capture_proc = None
    app.state.past_sessions = []

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    app.state.ollama_model = model
    app.state.ollama_client = OllamaClient(base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    app.state.extractor = ExtractorWorker(
        state=app.state.session,
        hub=app.state.hub,
        client=app.state.ollama_client,
        model=model,
    )
    app.state.extractor.start()

    yield

    await app.state.extractor.stop()
    proc = app.state.capture_proc
    if proc is not None and proc.returncode is None:
        proc.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
```

Add a small helper near `_segment_to_dict`:

```python
def _insight_to_dict(ins: Insight) -> dict:
    return {
        "id": ins.id,
        "session_id": ins.session_id,
        "category": ins.category,
        "text": ins.text,
        "original_text": ins.original_text,
        "source_quote": ins.source_quote,
        "language": ins.language,
        "confidence": ins.confidence,
        "status": ins.status,
        "created_at_iso": ins.created_at_iso,
    }


def _find_insight(app: FastAPI, ins_id: str) -> tuple[int, Insight] | None:
    for i, ins in enumerate(app.state.session.insights):
        if ins.id == ins_id:
            return i, ins
    return None


def _replace_insight(app: FastAPI, idx: int, new: Insight) -> None:
    app.state.session.insights[idx] = new
```

Add a Pydantic body model and the four routes near the existing route definitions (placement: after the history routes, before `@app.websocket("/ws")`):

```python
class EditBody(BaseModel):
    text: str


@app.get("/insights")
async def list_insights() -> dict:
    return {"insights": [_insight_to_dict(i) for i in app.state.session.insights]}


@app.post("/insights/{ins_id}/approve")
async def approve_insight(ins_id: str) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    from dataclasses import replace
    new = replace(ins, status="approved")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.post("/insights/{ins_id}/decline")
async def decline_insight(ins_id: str) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    from dataclasses import replace
    new = replace(ins, status="declined")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.post("/insights/{ins_id}/edit")
async def edit_insight(ins_id: str, body: EditBody) -> dict:
    found = _find_insight(app, ins_id)
    if found is None:
        raise HTTPException(status_code=404, detail="insight not found")
    idx, ins = found
    new_text = body.text.strip()
    if not new_text or len(new_text) > 500:
        raise HTTPException(status_code=400, detail="text must be 1..500 chars")
    from dataclasses import replace
    new = replace(ins, text=new_text, status="pending")
    _replace_insight(app, idx, new)
    await app.state.hub.broadcast({
        "type": "insight_update",
        "id": new.id,
        "status": new.status,
        "text": new.text,
    })
    return {"insight": _insight_to_dict(new)}


@app.get("/ai/status")
async def ai_status() -> dict:
    result = await app.state.ollama_client.health(model=app.state.ollama_model)
    return {"state": result, "model": app.state.ollama_model}
```

Also: in the existing `WS /ws` route, the initial snapshot frame should include the current AI status. After the existing initial `state` send, add another send. Locate this block:

```python
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    hub: Hub = app.state.hub
    await hub.connect(ws)
    s: SessionState = app.state.session
    await ws.send_json({
        "type": "state",
        "state": s.recording_state,
        "session_id": s.session_id,
    })
```

Right after the `await ws.send_json(...)` for state, append:

```python
    # Also send a snapshot of any existing insights, so a late client catches up.
    for ins in s.insights:
        await ws.send_json({"type": "insight", "insight": _insight_to_dict(ins)})
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests/test_insights_api.py -v
```

Expected: 6 passed. (`test_ai_status_endpoint` passes because `health()` cleanly returns `"offline"` when Ollama isn't running.)

- [ ] **Step 5: Run the full backend suite**

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -v
```

Expected: all tests pass. Approximately 47+ total now.

- [ ] **Step 6: Commit**

```bash
git add backend/server.py backend/tests/test_insights_api.py
git commit -m "backend: /insights routes + ExtractorWorker in lifespan"
```

---

### Task 8: UI types + WS hook updates

**Files:**
- Modify: `/Users/danila/Documents/doings/ui/src/lib/types.ts`
- Modify: `/Users/danila/Documents/doings/ui/src/lib/useSessionWs.ts`

- [ ] **Step 1: Replace `ui/src/lib/types.ts` content**

```typescript
export type Segment = {
  id: string;
  session_id: string;
  text: string;
  start_s: number;
  end_s: number;
  lang: string;
};

export type PastSessionSummary = {
  session_id: string;
  ended_at_iso: string;
  segment_count: number;
  duration_s: number;
  languages: string[];
};

export type PastSession = {
  session_id: string;
  ended_at_iso: string;
  segments: Segment[];
};

export type InsightStatus = "pending" | "approved" | "declined";
export type InsightCategory = "functional" | "non_functional";

export type Insight = {
  id: string;
  session_id: string;
  category: InsightCategory;
  text: string;
  original_text: string;
  source_quote: string;
  language: string;
  confidence: number;
  status: InsightStatus;
  created_at_iso: string;
};

export type AiStatus = "ok" | "no_model" | "offline" | "unknown";

export type RecordingState =
  | "idle"
  | "recording"
  | "paused"
  | "stopping"
  | "disconnected";

export type WsMessage =
  | { type: "state"; state: Exclude<RecordingState, "disconnected">; session_id: string | null }
  | { type: "segment"; segment: Segment }
  | { type: "delivery"; id: string; status: string; attempts: number }
  | { type: "insight"; insight: Insight }
  | { type: "insight_update"; id: string; status: InsightStatus; text: string }
  | { type: "ai_status"; state: Exclude<AiStatus, "unknown">; model: string; error?: string };
```

- [ ] **Step 2: Update `ui/src/lib/useSessionWs.ts` to handle new messages**

Replace the contents of the file:

```typescript
import { useEffect, useRef, useState } from "react";
import type { AiStatus, Insight, RecordingState, Segment, WsMessage } from "./types";

export type SessionView = {
  state: RecordingState;
  sessionId: string | null;
  segments: Segment[];
  insights: Insight[];
  aiStatus: AiStatus;
};

const RECONNECT_BACKOFF_MS = [1000, 2000, 4000, 8000, 10000];

export function useSessionWs(): SessionView {
  const [state, setState] = useState<RecordingState>("disconnected");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [aiStatus, setAiStatus] = useState<AiStatus>("unknown");
  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/ws`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
      };

      ws.onmessage = (ev) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type === "state") {
          setState(msg.state);
          setSessionId((prevId) => {
            if (msg.session_id && msg.session_id !== prevId) {
              setSegments([]);
              setInsights([]);
            }
            return msg.session_id;
          });
        } else if (msg.type === "segment") {
          setSegments((prev) => [...prev, msg.segment]);
        } else if (msg.type === "insight") {
          setInsights((prev) => {
            // Late snapshots may re-send; replace by id if present.
            const idx = prev.findIndex((i) => i.id === msg.insight.id);
            if (idx >= 0) {
              const next = prev.slice();
              next[idx] = msg.insight;
              return next;
            }
            return [...prev, msg.insight];
          });
        } else if (msg.type === "insight_update") {
          setInsights((prev) =>
            prev.map((i) =>
              i.id === msg.id ? { ...i, status: msg.status, text: msg.text } : i,
            ),
          );
        } else if (msg.type === "ai_status") {
          setAiStatus(msg.state);
        }
        // "delivery" messages ignored in this UI.
      };

      ws.onclose = () => {
        if (cancelled) return;
        setState("disconnected");
        const delay =
          RECONNECT_BACKOFF_MS[
            Math.min(attemptRef.current, RECONNECT_BACKOFF_MS.length - 1)
          ];
        attemptRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  return { state, sessionId, segments, insights, aiStatus };
}
```

- [ ] **Step 3: Type-check**

```bash
cd /Users/danila/Documents/doings/ui && npx tsc --noEmit
```

Expected: errors about old `Insight` shape used elsewhere — we fix them in the next tasks. **Stop here on first error**; that's expected because InsightCard/InsightsPanel still reference the old shape. Note them and continue.

If there are errors only in `InsightCard.tsx` and `InsightsPanel.tsx`, that's the expected fail-forward path. Move on.

- [ ] **Step 4: Commit**

```bash
cd /Users/danila/Documents/doings
git add ui/src/lib/types.ts ui/src/lib/useSessionWs.ts
git commit -m "ui: handle insight/insight_update/ai_status WS messages"
```

---

### Task 9: API helpers for insights

**Files:**
- Modify: `/Users/danila/Documents/doings/ui/src/lib/api.ts`

- [ ] **Step 1: Append to `ui/src/lib/api.ts`**

Add these functions to the existing file (do not remove `startSession`, `stopSession`, `pauseSession`, etc.):

```typescript
import type { Insight } from "./types";

export async function approveInsight(id: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/approve`, { method: "POST" });
  if (!r.ok) throw new Error(`approve failed: ${r.status}`);
  return (await r.json()).insight;
}

export async function declineInsight(id: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/decline`, { method: "POST" });
  if (!r.ok) throw new Error(`decline failed: ${r.status}`);
  return (await r.json()).insight;
}

export async function editInsight(id: string, text: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`edit failed: ${r.status}`);
  return (await r.json()).insight;
}
```

(The existing file already has an `import type` at the top — TS will collapse the new `import type { Insight }` with it if you prefer; either form compiles.)

- [ ] **Step 2: Type-check**

```bash
cd /Users/danila/Documents/doings/ui && npx tsc --noEmit
```

Expected: same pre-existing errors in `InsightCard.tsx` / `InsightsPanel.tsx`. No new ones.

- [ ] **Step 3: Commit**

```bash
cd /Users/danila/Documents/doings
git add ui/src/lib/api.ts
git commit -m "ui: api helpers for approve/decline/edit insights"
```

---

### Task 10: InsightCard with Approve / Edit / Decline

**Files:**
- Modify: `/Users/danila/Documents/doings/ui/src/components/InsightCard.tsx`

- [ ] **Step 1: Replace the file contents**

```typescript
import { useState } from "react";
import { approveInsight, declineInsight, editInsight } from "../lib/api";
import type { Insight } from "../lib/types";
import { cn } from "../lib/utils";

type Props = { insight: Insight };

const CATEGORY_LABEL = {
  functional: "Functional",
  non_functional: "Non-functional",
} as const;

const CATEGORY_CLASS = {
  functional: "bg-neon-cyan/15 text-neon-cyan border-neon-cyan/40",
  non_functional: "bg-neon-amber/15 text-neon-amber border-neon-amber/40",
} as const;

export default function InsightCard({ insight }: Props) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(insight.text);

  const acted = insight.status !== "pending";

  const run = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleEditOpen = () => {
    setDraft(insight.text);
    setEditing(true);
  };

  const handleEditSave = () =>
    run(async () => {
      const t = draft.trim();
      if (!t) return;
      await editInsight(insight.id, t);
      setEditing(false);
    });

  return (
    <div
      className={cn(
        "rounded-xl border border-white/10 bg-white/5 p-3 transition-opacity",
        insight.status === "declined" && "opacity-40",
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border",
            CATEGORY_CLASS[insight.category],
          )}
        >
          {CATEGORY_LABEL[insight.category]}
        </span>
        <span className="text-[10px] text-white/30 ml-auto tabular-nums">
          {(insight.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full text-sm bg-black/40 border border-white/10 rounded-md px-2 py-1.5 text-white focus:outline-none focus:border-neon-cyan/60"
        />
      ) : (
        <p className="text-sm text-white leading-snug">{insight.text}</p>
      )}

      {insight.source_quote && !editing && (
        <p className="mt-1.5 text-xs text-white/40 italic leading-snug">
          “{insight.source_quote}”
        </p>
      )}

      {!acted && !editing && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => run(() => approveInsight(insight.id))}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-green/15 text-neon-green border border-neon-green/30 hover:bg-neon-green/25 disabled:opacity-50"
          >
            ✓ Approve
          </button>
          <button
            onClick={handleEditOpen}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-white/10 text-white border border-white/20 hover:bg-white/15 disabled:opacity-50"
          >
            ✎ Edit
          </button>
          <button
            onClick={() => run(() => declineInsight(insight.id))}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-pink/15 text-neon-pink border border-neon-pink/30 hover:bg-neon-pink/25 disabled:opacity-50"
          >
            ✗ Decline
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={handleEditSave}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/30 hover:bg-neon-cyan/25 disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-white/10 text-white/70 border border-white/20 hover:bg-white/15 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}

      {acted && !editing && (
        <p className="mt-2 text-[10px] text-white/40 uppercase tracking-wider">
          {insight.status}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/components/InsightCard.tsx
git commit -m "ui: InsightCard with Approve/Edit/Decline wired to backend"
```

---

### Task 11: InsightsPanel sources from hook + status badge

**Files:**
- Modify: `/Users/danila/Documents/doings/ui/src/components/InsightsPanel.tsx`
- Modify: `/Users/danila/Documents/doings/ui/src/App.tsx`

- [ ] **Step 1: Replace `ui/src/components/InsightsPanel.tsx`**

```typescript
import type { AiStatus, Insight } from "../lib/types";
import GlassCard from "./GlassCard";
import InsightCard from "./InsightCard";

type Props = {
  insights: Insight[];
  aiStatus: AiStatus;
};

const STATUS_DOT: Record<AiStatus, string> = {
  ok: "bg-neon-green",
  no_model: "bg-neon-amber",
  offline: "bg-neon-pink",
  unknown: "bg-white/30",
};

const STATUS_LABEL: Record<AiStatus, string> = {
  ok: "AI online",
  no_model: "Model not pulled",
  offline: "AI offline",
  unknown: "AI status unknown",
};

function emptyCopy(status: AiStatus): { title: string; sub: string } {
  if (status === "offline") {
    return {
      title: "AI offline",
      sub: "Start Ollama (`ollama serve`) and the panel will start populating.",
    };
  }
  if (status === "no_model") {
    return {
      title: "Model not installed",
      sub: "Run `ollama pull phi3` (or whichever model OLLAMA_MODEL points at) and try again.",
    };
  }
  return {
    title: "No requirements yet",
    sub: "Speak about what the system should do; requirements will appear here.",
  };
}

export default function InsightsPanel({ insights, aiStatus }: Props) {
  const pending = insights.filter((i) => i.status === "pending").length;
  const empty = emptyCopy(aiStatus);

  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          AI Insights
        </h2>
        <div className="flex items-center gap-3">
          {insights.length > 0 && (
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              {pending} pending
            </span>
          )}
          <span
            className="flex items-center gap-1.5 text-[10px] text-white/60 uppercase tracking-wider"
            title={STATUS_LABEL[aiStatus]}
          >
            <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[aiStatus]}`} />
            {aiStatus}
          </span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-2">
        {insights.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-white/40 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-xs">
              <div className="text-white/60 mb-2">{empty.title}</div>
              <div className="text-xs">{empty.sub}</div>
            </div>
          </div>
        ) : (
          insights.map((insight) => <InsightCard key={insight.id} insight={insight} />)
        )}
      </div>
    </GlassCard>
  );
}
```

- [ ] **Step 2: Wire the new props in `ui/src/App.tsx`**

Find the existing `<InsightsPanel />` usage and replace it:

```typescript
<InsightsPanel insights={session.insights} aiStatus={session.aiStatus} />
```

- [ ] **Step 3: Type-check + build**

```bash
cd /Users/danila/Documents/doings/ui && npx tsc --noEmit && npm run build
```

Expected: clean type-check, successful build.

- [ ] **Step 4: Commit**

```bash
cd /Users/danila/Documents/doings
git add ui/src/components/InsightsPanel.tsx ui/src/App.tsx
git commit -m "ui: InsightsPanel reads from hook; AI status badge in header"
```

---

### Task 12: README — Ollama setup

**Files:**
- Modify: `/Users/danila/Documents/doings/README.md`

- [ ] **Step 1: Update the README**

Open `README.md`. Find the "Requirements" section and add a bullet for Ollama:

```
- **Ollama** (for Step 3 AI insights): `brew install ollama` (or download from https://ollama.com). Then `ollama serve` and `ollama pull phi3`.
```

In the "Running the dashboard" section, before "Terminal 1 — local echo endpoint", add a new "Terminal 0 — Ollama (optional, enables AI insights)" block:

```
### Terminal 0 — Ollama (optional, enables AI insights)

```bash
ollama serve
```

In another shell (one-time per model):

```bash
ollama pull phi3       # default — fast (~2.4GB)
# Optional alternatives for A/B testing:
ollama pull mistral    # stronger German (~4GB)
ollama pull llama3.1   # strongest reasoning (~5GB)
```

Skip this terminal if you don't want AI insights — the rest of the dashboard still works.
```

In Terminal 2 (backend), add `OLLAMA_MODEL` to the env vars and document available env vars:

```bash
OLLAMA_MODEL=phi3 \
DOINGS_ENDPOINT=http://localhost:8001/stt \
PYTHONPATH=. backend/.venv/bin/uvicorn backend.server:app --reload --port 8000
```

In the Troubleshooting table, add:

```
| AI insights panel says "AI offline" | `ollama serve` isn't running. Start it. The panel reconnects within ~5s of the next tick. |
| AI insights panel says "Model not installed" | Run `ollama pull phi3` (or whatever `OLLAMA_MODEL` is set to). |
| Insights are too few / many | Tune `EXTRACTOR_CONFIDENCE_FLOOR` (default `0.6`). Lower → more pass through; higher → stricter. Restart backend after changing env vars. |
```

In the "Build order" section, change Step 3 from 🔲 to 🚧 (in progress) and Step 4 stays 🔲.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README covers Ollama setup + env-tunable filter knobs"
```

---

### Task 13: End-to-end manual acceptance

This task is **manual**. Verify the whole pipeline works.

- [ ] **Step 1: Pull the default model**

```bash
ollama pull phi3
```

(One-time per machine. Expect ~2.4GB download.)

- [ ] **Step 2: Start the four processes**

Terminal 0:
```bash
ollama serve
```

Terminal 1 (in repo root):
```bash
PYTHONPATH=. backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001
```

Terminal 2 (in repo root):
```bash
OLLAMA_MODEL=phi3 \
DOINGS_ENDPOINT=http://localhost:8001/stt \
PYTHONPATH=. backend/.venv/bin/uvicorn backend.server:app --reload --port 8000
```

Terminal 3 (in `ui/`):
```bash
npm run dev
```

Open http://localhost:5173.

- [ ] **Step 3: AI status badge**

In the AI Insights panel header you should see a green dot + "ok" within a few seconds. If yellow ("no_model"), run `ollama pull phi3` and reload. If pink ("offline"), check `ollama serve` is running.

- [ ] **Step 4: Speak some requirements**

Press ▶ Start. Speak slowly and clearly:
- *"Das System muss mindestens fünfhundert Nutzer unterstützen."*
- *"Authentication should use OAuth 2.0."*
- *"The export feature has to support both JSON and CSV."*

Within ~5–12 seconds of each utterance, requirement cards should appear in the Insights panel.

- [ ] **Step 5: Approve / Edit / Decline**

- Click Approve on one. It should show "approved" footer text.
- Click Edit on another. Textarea opens. Change the wording. Save. Card returns to view with the new text; still pending.
- Click Decline on a third. Card dims.

- [ ] **Step 6: Stop and start a new session**

Press ■ Stop. Then press ▶ Start. The transcript and insights should both clear. Previous insights should not reappear.

- [ ] **Step 7: Test model swap**

In terminal 2, Ctrl-C the backend. Restart with `OLLAMA_MODEL=mistral` (after running `ollama pull mistral`). Refresh the UI. Speak the same German sentence. Compare quality and latency to phi3. Note observations in a scratchpad.

- [ ] **Step 8: Run full test suite to confirm no regressions**

```bash
cd /Users/danila/Documents/doings
PYTHONPATH=. capture/.venv/bin/pytest capture/tests -q
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q
cd ui && npx tsc --noEmit
```

Expected: capture and backend suites green, UI type-check clean.

- [ ] **Step 9: No commit** — verification only.

If anything fails, file a follow-up task in this plan or fix inline.

---

## Self-Review Notes

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| Ollama client + health check | Task 3 |
| Prompt template with schema + is_requirement + reasoning | Task 4 |
| 5-gate quality filter | Task 5 |
| ExtractorWorker timer + skip-if-busy + ai_status broadcast | Task 6 |
| Insight dataclass + status | Task 1 |
| SessionState.insights + reset behavior | Task 2 |
| Endpoints `/insights`, approve/decline/edit, `/ai/status` | Task 7 |
| ExtractorWorker started in lifespan with env-configurable model | Task 7 |
| WS message types `insight` / `insight_update` / `ai_status` | Task 7 (broadcast) + Task 8 (handler) |
| UI types: `InsightStatus`, drop `rejected`, `AiStatus`, narrow category | Task 8 |
| API helpers approve/decline/edit | Task 9 |
| InsightCard with Approve / Edit / Decline | Task 10 |
| InsightsPanel sources from hook + status badge + per-state empty copy | Task 11 |
| Env vars documented + Ollama setup steps | Task 12 |
| Manual acceptance | Task 13 |

**Type consistency:**
- `Insight.category` is `"functional" | "non_functional"` in both Python (Task 1) and TS (Task 8). `chatter`, `action_item`, `decision` are dropped.
- `InsightStatus` is `pending | approved | declined` on both sides. The Step 2.5 scaffold's `rejected` is renamed to `declined`.
- `_insight_to_dict` keys match the TS `Insight` shape (`category`, `text`, `original_text`, `source_quote`, `language`, `confidence`, `status`, `created_at_iso`).
- WS message types in Python (Task 6/7 broadcasts) match TS `WsMessage` union (Task 8).
- `FilterConfig` field names match env-var names: `EXTRACTOR_CONFIDENCE_FLOOR`, `EXTRACTOR_QUOTE_MATCH_RATIO`, `EXTRACTOR_REQUIRE_SOURCE_QUOTE`.
- `ExtractorWorker.__init__` matches `Task 6` test instantiations (kwargs only).

**Placeholder scan:** No TBDs, no "handle X appropriately." Each step contains complete code or a complete command.

**Caveats:**
- Task 8 Step 3 is the only place that intentionally leaves type errors temporarily; Task 10 closes them. The plan flags this explicitly.
- Task 13 is manual and depends on the user's environment having Ollama installed. The plan tells them how to install.
- `_insight_to_dict` is defined in both `backend/extractor.py` and `backend/server.py` per the plan. That's two small copies of the same dict-builder; intentional to keep extractor self-contained for tests. If preferred, it can be moved to `insights.py` in a small follow-up — not in scope here.
