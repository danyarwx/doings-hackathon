"""Jira Cloud REST API v3 client (Basic auth: email + API token).

Builds ADF (Atlassian Document Format) descriptions on the fly so we don't
need to depend on Jira's plain-text rendering legacy. Only the shapes we
actually emit are implemented — headings, paragraphs, bullet lists.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx


def _adf_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _adf_heading(text: str, level: int = 2) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _adf_bullet_list(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": it}]}],
            }
            for it in items
        ],
    }


def build_description_adf(*, requirement: dict, decisions: list[dict]) -> dict:
    """Build a Jira ADF description for one requirement.

    Decisions are pinned at the top of every issue.
    """
    content: list[dict] = []

    decision_summaries = [d.get("summary", "").strip() for d in decisions if d.get("summary", "").strip()]
    if decision_summaries:
        content.append(_adf_heading("Meeting decisions", level=2))
        content.append(_adf_bullet_list(decision_summaries))

    story = (requirement.get("description") or {}).get("user_story") or {}
    given = story.get("given", "").strip()
    when = story.get("when", "").strip()
    then = story.get("then", "").strip()
    if given or when or then:
        content.append(_adf_heading("User story", level=2))
        if given:
            content.append(_adf_paragraph(f"Given {given}"))
        if when:
            content.append(_adf_paragraph(f"When {when}"))
        if then:
            content.append(_adf_paragraph(f"Then {then}"))

    ac = (requirement.get("description") or {}).get("acceptance_criteria") or []
    ac = [c.strip() for c in ac if isinstance(c, str) and c.strip()]
    if ac:
        content.append(_adf_heading("Acceptance criteria", level=2))
        content.append(_adf_bullet_list(ac))

    invest = (requirement.get("description") or {}).get("invest_validation") or {}
    invest_lines = [
        f"{name.capitalize()}: {'✓' if invest.get(name, False) else '✗'}"
        for name in ("independent", "negotiable", "valuable", "estimable", "small", "testable")
    ]
    if invest_lines:
        content.append(_adf_heading("INVEST validation", level=2))
        content.append(_adf_bullet_list(invest_lines))

    return {"type": "doc", "version": 1, "content": content}


def build_issue_payload(*, requirement: dict, decisions: list[dict], project_key: str) -> dict:
    """Build the body for POST /rest/api/3/issue."""
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": requirement.get("summary", "").strip() or "(no summary)",
        "issuetype": {"name": requirement.get("issuetype", "Story")},
        "description": build_description_adf(requirement=requirement, decisions=decisions),
    }
    labels = requirement.get("labels") or []
    if labels:
        fields["labels"] = [l for l in labels if isinstance(l, str) and l.strip()]
    priority = requirement.get("priority")
    if priority:
        fields["priority"] = {"name": priority.capitalize()}
    # story_points is a custom field on most Jira projects; intentionally not
    # sent — different orgs use different customfield IDs. The UI keeps the
    # number visible so users can fill it in Jira manually.
    return {"fields": fields}


class JiraClient:
    """Minimal Jira Cloud REST v3 client. Holds creds in memory."""

    def __init__(
        self,
        *,
        base_url: str = "",
        email: str = "",
        api_token: str = "",
        project_key: str = "",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._email = email
        self._token = api_token
        self._project = project_key

    def set_url(self, v: str) -> None:
        self._base = v.strip().rstrip("/")

    def set_email(self, v: str) -> None:
        self._email = v.strip()

    def set_token(self, v: str) -> None:
        self._token = v.strip()

    def set_project(self, v: str) -> None:
        self._project = v.strip()

    @property
    def url_set(self) -> bool:
        return bool(self._base)

    @property
    def email_set(self) -> bool:
        return bool(self._email)

    @property
    def token_set(self) -> bool:
        return bool(self._token)

    @property
    def project_set(self) -> bool:
        return bool(self._project)

    @property
    def fully_configured(self) -> bool:
        return self.url_set and self.email_set and self.token_set and self.project_set

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def project(self) -> str:
        return self._project

    def _auth_header(self) -> dict:
        raw = f"{self._email}:{self._token}".encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def create_issue(
        self,
        *,
        requirement: dict,
        decisions: list[dict],
        timeout_s: float = 30.0,
    ) -> dict:
        """POST /rest/api/3/issue. Returns {'key': '...', 'url': '...'} on success.

        Raises RuntimeError with the server's error message on failure.
        """
        if not self.fully_configured:
            raise RuntimeError("Jira is not fully configured")

        payload = build_issue_payload(
            requirement=requirement, decisions=decisions, project_key=self._project,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                r = await http.post(
                    f"{self._base}/rest/api/3/issue",
                    json=payload,
                    headers=self._auth_header(),
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Jira request failed: {exc}") from exc

        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            raise RuntimeError(f"Jira returned {r.status_code}: {body}")

        body = r.json()
        key = body.get("key")
        if not key:
            raise RuntimeError(f"Jira response missing 'key': {body}")
        return {"key": key, "url": f"{self._base}/browse/{key}"}
