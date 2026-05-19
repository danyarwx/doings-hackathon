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
