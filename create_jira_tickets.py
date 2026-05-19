"""
create_jira_tickets.py
======================
Reads requirements extracted by model.py and creates Jira issues via
the Jira Cloud REST API v3.

Usage
-----
    # From a JSON file produced by model.py
    python create_jira_tickets.py results.json

    # Pipe extraction output directly
    python create_jira_tickets.py -

    # Preview payloads without posting
    python create_jira_tickets.py results.json --dry-run

Required environment variables
-------------------------------
    JIRA_BASE_URL      https://yourcompany.atlassian.net
    JIRA_EMAIL         Atlassian account email
    JIRA_API_TOKEN     API token from id.atlassian.com/manage-profile/security/api-tokens
    JIRA_PROJECT_KEY   Board key, e.g. "PROJ"

Optional environment variables
-------------------------------
    JIRA_STORY_POINTS_FIELD  Custom field for story points (default: customfield_10016)
    JIRA_ASSIGNEE_MAP        JSON dict mapping name → Jira accountId
                             e.g. '{"Alice":"5b10a2...","Bob":"5b10a3..."}'

Input format
------------
Accepts the full extraction result object from model.py:
    {
      "requirements": [...],
      "action_items": [...],
      "decisions": [...],
      "topics": [...]
    }
or a list of such objects, or a list of requirement objects directly.
Only the "requirements" array is used for ticket creation.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("create_jira_tickets")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

JIRA_BASE_URL: str        = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL: str           = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN: str       = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY: str     = os.getenv("JIRA_PROJECT_KEY", "")
STORY_POINTS_FIELD: str   = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10016")

_assignee_map_raw = os.getenv("JIRA_ASSIGNEE_MAP", "{}")
try:
    ASSIGNEE_MAP: dict[str, str] = json.loads(_assignee_map_raw)
except json.JSONDecodeError:
    log.warning("JIRA_ASSIGNEE_MAP is not valid JSON — assignee mapping disabled")
    ASSIGNEE_MAP = {}

# Priority mapping: model output → Jira priority name
PRIORITY_MAP: dict[str, str] = {
    "high":   "High",
    "medium": "Medium",
    "low":    "Low",
}

# ---------------------------------------------------------------------------
# Atlassian Document Format (ADF) helpers
# ---------------------------------------------------------------------------

def _text(content: str, bold: bool = False) -> dict:
    node: dict[str, Any] = {"type": "text", "text": content}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def _paragraph(*inline_nodes: dict) -> dict:
    return {"type": "paragraph", "content": list(inline_nodes)}


def _heading(text: str, level: int = 3) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [_text(text)],
    }


def _bullet_list(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [_paragraph(_text(item))],
            }
            for item in items
        ],
    }


def _rule() -> dict:
    return {"type": "rule"}


def _invest_row(label: str, passed: bool) -> dict:
    mark = "✅" if passed else "❌"
    return {
        "type": "listItem",
        "content": [_paragraph(_text(f"{mark}  {label}"))],
    }


def build_adf_description(req: dict) -> dict:
    """
    Convert a requirement object (from model.py SYSTEM_PROMPT schema) into
    Atlassian Document Format for the Jira REST API v3 description field.
    """
    content: list[dict] = []
    desc = req.get("description") or {}

    # ── User Story ────────────────────────────────────────────────────────
    us = desc.get("user_story") or {}
    if us:
        content.append(_heading("User Story", level=3))
        if us.get("given"):
            content.append(_paragraph(
                _text("Given  ", bold=True),
                _text(us["given"]),
            ))
        if us.get("when"):
            content.append(_paragraph(
                _text("When  ", bold=True),
                _text(us["when"]),
            ))
        if us.get("then"):
            content.append(_paragraph(
                _text("Then  ", bold=True),
                _text(us["then"]),
            ))

    # ── Acceptance Criteria ───────────────────────────────────────────────
    ac = desc.get("acceptance_criteria") or []
    if ac:
        content.append(_rule())
        content.append(_heading("Acceptance Criteria", level=3))
        content.append(_bullet_list(ac))

    # ── INVEST Validation ─────────────────────────────────────────────────
    invest = desc.get("invest_validation") or {}
    invest_labels = [
        ("Independent",  invest.get("independent",  False)),
        ("Negotiable",   invest.get("negotiable",   False)),
        ("Valuable",     invest.get("valuable",     False)),
        ("Estimable",    invest.get("estimable",    False)),
        ("Small",        invest.get("small",        False)),
        ("Testable",     invest.get("testable",     False)),
    ]
    if any(v is not None for _, v in invest_labels):
        content.append(_rule())
        content.append(_heading("INVEST Validation", level=3))
        content.append({
            "type": "bulletList",
            "content": [_invest_row(label, bool(val)) for label, val in invest_labels],
        })

    # ── Fallback: plain description ───────────────────────────────────────
    if not content:
        raw = req.get("description") or ""
        if isinstance(raw, str) and raw:
            content.append(_paragraph(_text(raw)))

    # ADF requires at least one content node
    if not content:
        content.append(_paragraph(_text("(No description provided)")))

    return {"type": "doc", "version": 1, "content": content}


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_jira_payload(req: dict) -> dict:
    """Map a single requirement dict to a Jira REST API v3 issue payload."""
    fields: dict[str, Any] = {
        "project":     {"key": JIRA_PROJECT_KEY},
        "summary":     req.get("summary", "(no summary)"),
        "issuetype":   {"name": req.get("issuetype", "Story")},
        "description": build_adf_description(req),
    }

    # Priority
    priority_raw = (req.get("priority") or "medium").lower()
    fields["priority"] = {"name": PRIORITY_MAP.get(priority_raw, "Medium")}

    # Labels (Jira labels must be single words — replace spaces with _)
    labels = req.get("labels") or []
    if labels:
        fields["labels"] = [lbl.replace(" ", "_") for lbl in labels]

    # Due date (Jira expects YYYY-MM-DD)
    duedate = req.get("duedate")
    if duedate:
        fields["duedate"] = duedate

    # Story points (custom field — default customfield_10016)
    sp = req.get("story_points")
    if sp is not None:
        try:
            fields[STORY_POINTS_FIELD] = float(sp)
        except (TypeError, ValueError):
            pass

    # Assignee — model outputs a name; Jira v3 requires accountId
    assignee_name = req.get("assignee")
    if assignee_name and assignee_name in ASSIGNEE_MAP:
        fields["assignee"] = {"accountId": ASSIGNEE_MAP[assignee_name]}
    elif assignee_name:
        log.warning(
            "Assignee %r not found in JIRA_ASSIGNEE_MAP — skipping assignee field",
            assignee_name,
        )

    return {"fields": fields}


# ---------------------------------------------------------------------------
# Jira API client
# ---------------------------------------------------------------------------

def _auth_header() -> str:
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return f"Basic {token}"


def create_issue(payload: dict, client: httpx.Client) -> dict:
    """POST a single issue to Jira and return the created issue dict."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    resp = client.post(
        url,
        json=payload,
        headers={
            "Authorization": _auth_header(),
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        },
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def load_requirements(source: str) -> list[dict]:
    """
    Accept multiple input shapes:
      - A single extraction object  {"requirements": [...], ...}
      - A list of extraction objects [{"requirements": [...]}, ...]
      - A bare list of requirement objects [{"summary": ...}, ...]
    """
    if source == "-":
        raw = sys.stdin.read()
    else:
        with open(source, encoding="utf-8") as fh:
            raw = fh.read()

    data = json.loads(raw)

    if isinstance(data, list):
        # Could be a list of extraction results or a direct list of requirements
        if data and "requirements" in data[0]:
            reqs = []
            for item in data:
                reqs.extend(item.get("requirements") or [])
            return reqs
        return data  # assume direct list of requirement dicts

    if isinstance(data, dict):
        return data.get("requirements") or []

    raise ValueError(f"Unexpected JSON shape: {type(data)}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_env() -> list[str]:
    missing = []
    for var, val in [
        ("JIRA_BASE_URL",     JIRA_BASE_URL),
        ("JIRA_EMAIL",        JIRA_EMAIL),
        ("JIRA_API_TOKEN",    JIRA_API_TOKEN),
        ("JIRA_PROJECT_KEY",  JIRA_PROJECT_KEY),
    ]:
        if not val:
            missing.append(var)
    return missing


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Jira tickets from model.py extraction output",
    )
    parser.add_argument(
        "source",
        help="Path to extraction JSON file, or '-' to read from stdin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Jira payloads without making API calls",
    )
    args = parser.parse_args()

    if not args.dry_run:
        missing = validate_env()
        if missing:
            log.error("Missing required environment variables: %s", ", ".join(missing))
            sys.exit(1)

    requirements = load_requirements(args.source)
    if not requirements:
        log.warning("No requirements found in input — nothing to create")
        return

    log.info("Found %d requirement(s) to process", len(requirements))

    created: list[dict] = []
    failed: list[dict]  = []

    with httpx.Client(timeout=30) as client:
        for i, req in enumerate(requirements, start=1):
            summary = req.get("summary", f"<requirement {i}>")
            payload = build_jira_payload(req)

            if args.dry_run:
                print(f"\n--- Dry run: requirement {i} ---")
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                continue

            try:
                result = create_issue(payload, client)
                key  = result.get("key", "?")
                link = f"{JIRA_BASE_URL}/browse/{key}"
                log.info("[%d/%d] Created %s  %s  →  %s", i, len(requirements), key, summary, link)
                created.append({"key": key, "summary": summary, "url": link})
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:400]
                log.error("[%d/%d] Failed to create %r: HTTP %d  %s", i, len(requirements), summary, exc.response.status_code, body)
                failed.append({"summary": summary, "error": body})
            except Exception as exc:
                log.error("[%d/%d] Unexpected error for %r: %s", i, len(requirements), summary, exc)
                failed.append({"summary": summary, "error": str(exc)})

    if args.dry_run:
        return

    print(f"\n{'='*60}")
    print(f"Created : {len(created)}")
    print(f"Failed  : {len(failed)}")
    if created:
        print("\nCreated tickets:")
        for t in created:
            print(f"  {t['key']}  {t['url']}")
    if failed:
        print("\nFailed tickets:")
        for t in failed:
            print(f"  {t['summary']}")
            print(f"    {t['error'][:120]}")


if __name__ == "__main__":
    main()
