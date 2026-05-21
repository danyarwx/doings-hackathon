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

BAD examples (skip these — do NOT include them in output):
- "product requirements" — noun phrase, no verb
- "document for the new" — fragment, incomplete clause
- "how many?" — question, not a directive
- "Yeah." — chatter
- "It would be sales made." — ambiguous fragment, no clear requirement

GOOD examples (these are real requirements):
- "The dashboard must show monthly revenue." — modal + clause → explicit
- "We need to support German language input." — intent + clause → explicit
- "Sales reports should export to CSV." — modal + clause → explicit

ONLY emit entries you believe ARE requirements. Skip everything else. If nothing qualifies, return {"requirements": []}.

`source_quote` MUST be a verbatim span copied from the FOCUS utterance — no paraphrasing, no shortening. If you can't quote it exactly, skip the entry.

`certainty` is "explicit" if the FOCUS utterance contains the modal/intent verb verbatim, or "implied" if you inferred the requirement using CONTEXT (e.g., resolved a pronoun).

`detail` is ONE short sentence (≤ 25 words) that adds USEFUL context drawn from the FOCUS or CONTEXT — surrounding constraints, who/what/where, related decisions. It MUST NOT contradict the transcript and MUST NOT invent specifics that aren't in it. Don't just repeat `text` in different words; only emit a detail when there is real extra information to add. If there is nothing useful to add, return an empty string.

Output the requirement `text` in the same language as the FOCUS (de stays de, en stays en). One entry per distinct requirement.

SCHEMA
{
  "requirements": [
    {
      "text": "<requirement in source language, complete clause>",
      "category": "functional" | "non_functional",
      "source_quote": "<verbatim span from FOCUS>",
      "detail": "<one short sentence of grounded context, or empty string>",
      "language": "de" | "en",
      "certainty": "explicit" | "implied"
    }
  ]
}
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
