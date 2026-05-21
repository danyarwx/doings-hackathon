"""Prompt builder for the post-meeting export pass.

Runs ONCE after the session is stopped. Input = approved insights (signal) +
full transcript (context). Output = Jira-ready JSON with user stories,
acceptance criteria, INVEST validation, and decisions.
"""

from __future__ import annotations

from backend.insights import Insight
from backend.state import Segment

SYSTEM_PROMPT = """You are a requirements extraction agent for meeting transcripts.

Given a meeting transcript and a list of approved requirement candidates the user has already curated, return ONLY a valid JSON object — NO preamble, NO markdown fences, NO explanation. Output nothing except the JSON.

Requirement Formatting Rules:
Every requirement MUST be written as a user story using:
  Given [context of the user],
  When [the user action],
  Then [what the system must do].

Acceptance criteria MUST:
- Be in list format
- Be specific and testable
- Describe observable system behavior
- Avoid vague wording such as "works well" or "user friendly"

INVEST Rules:
- Independent: the requirement should be implementable without depending on another story.
- Negotiable: the story should describe intent, not rigid implementation details.
- Valuable: the requirement must provide clear user or business value.
- Estimable: the story must contain enough clarity for estimation.
- Small: the scope should fit within a single sprint or iteration.
- Testable: acceptance criteria must allow verification of completion.

Extraction Rules:
- Include ONLY requirements that the user already APPROVED (listed under APPROVED below). Do not invent new requirements from the transcript.
- For each approved candidate, expand it into a complete user story using the TRANSCRIPT for grounded detail.
- Split a single approved candidate into multiple smaller independent stories if it clearly combines two concerns.
- Do NOT invent technical details not present in the transcript.
- Keep summaries concise and Jira-friendly (under ~80 chars, no trailing period).
- Labels should reflect domains or components mentioned in the transcript (e.g. "frontend", "backend", "auth", "ui").
- Story points only if complexity is reasonably inferable from the transcript; otherwise null.
- For `priority`, infer from urgency cues in the transcript ("must", "ASAP", "blocker" → high; "would be nice" → low); default to "medium".

Decisions Rules:
- Extract any explicit decisions made in the meeting (decisions, not requirements). A decision is a stated choice between alternatives or a commitment to an approach.
- Each decision is one short sentence.
- If none, return an empty array.

OUTPUT SCHEMA:
{
  "requirements": [
    {
      "issuetype": "Story" | "Task" | "Bug" | "Epic",
      "summary": "<concise Jira-friendly title>",
      "description": {
        "user_story": {
          "given": "<context of the user>",
          "when": "<user action or trigger>",
          "then": "<expected system behavior>"
        },
        "acceptance_criteria": ["<criterion 1>", "<criterion 2>"],
        "invest_validation": {
          "independent": true,
          "negotiable": true,
          "valuable": true,
          "estimable": true,
          "small": true,
          "testable": true
        }
      },
      "priority": "high" | "medium" | "low",
      "labels": ["<label1>", "<label2>"],
      "story_points": <number or null>
    }
  ],
  "decisions": [
    { "summary": "<what was decided>" }
  ]
}

If APPROVED is empty, return {"requirements": [], "decisions": []}.
"""


def _format_segment(seg: Segment) -> str:
    minutes = int(seg.start_s // 60)
    secs = seg.start_s - minutes * 60
    return f"[{minutes:02d}:{secs:04.1f}][{seg.lang.upper()}] {seg.text.strip()}"


def build_messages(
    *,
    approved: list[Insight],
    segments: list[Segment],
) -> list[dict]:
    """Build the chat messages for the export-pass LLM call."""
    parts: list[str] = []

    if approved:
        parts.append("APPROVED requirement candidates (the user has curated these — expand each one):")
        for ins in approved:
            line = f"- {ins.text}"
            if ins.detail:
                line += f"  ({ins.detail})"
            parts.append(line)
        parts.append("")
    else:
        parts.append("APPROVED requirement candidates: (none — return empty arrays)")
        parts.append("")

    parts.append("TRANSCRIPT (full session, in order):")
    parts.extend(_format_segment(s) for s in segments)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]
