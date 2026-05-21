"""Tests for the /jira/config and /export/push* routes + the ADF builder."""

import pytest

from backend.jira_client import (
    JiraClient,
    build_description_adf,
    build_issue_payload,
)


def _req(**overrides) -> dict:
    base = {
        "issuetype": "Story",
        "summary": "Show monthly revenue",
        "description": {
            "user_story": {
                "given": "A sales manager",
                "when": "They view the dashboard",
                "then": "Monthly revenue is rendered",
            },
            "acceptance_criteria": ["Currency formatted", "Updates daily"],
            "invest_validation": {
                "independent": True, "negotiable": True, "valuable": True,
                "estimable": True, "small": False, "testable": True,
            },
        },
        "priority": "high",
        "labels": ["frontend"],
        "story_points": 3,
    }
    base.update(overrides)
    return base


def test_adf_description_pins_decisions_at_the_top():
    adf = build_description_adf(
        requirement=_req(),
        decisions=[{"summary": "Use phi3 for live extraction"}, {"summary": "German is primary"}],
    )
    # Top-level block is a heading "Meeting decisions"
    first = adf["content"][0]
    assert first["type"] == "heading"
    assert first["content"][0]["text"] == "Meeting decisions"
    # Followed by a bullet list with both decisions
    bullets = adf["content"][1]
    assert bullets["type"] == "bulletList"
    texts = [b["content"][0]["content"][0]["text"] for b in bullets["content"]]
    assert texts == ["Use phi3 for live extraction", "German is primary"]


def test_adf_description_includes_user_story_and_ac():
    adf = build_description_adf(requirement=_req(), decisions=[])
    headings = [b["content"][0]["text"] for b in adf["content"] if b["type"] == "heading"]
    assert "User story" in headings
    assert "Acceptance criteria" in headings
    assert "INVEST validation" in headings


def test_adf_invest_marks_failing_items():
    adf = build_description_adf(requirement=_req(), decisions=[])
    # Find the INVEST bullet list and check 'Small' is ✗
    invest_section = False
    for block in adf["content"]:
        if block.get("type") == "heading" and block["content"][0]["text"] == "INVEST validation":
            invest_section = True
            continue
        if invest_section and block["type"] == "bulletList":
            texts = [b["content"][0]["content"][0]["text"] for b in block["content"]]
            assert "Small: ✗" in texts
            assert "Independent: ✓" in texts
            break


def test_issue_payload_sets_project_and_labels_and_priority():
    payload = build_issue_payload(
        requirement=_req(),
        decisions=[],
        project_key="DOINGS",
    )
    fields = payload["fields"]
    assert fields["project"] == {"key": "DOINGS"}
    assert fields["issuetype"] == {"name": "Story"}
    assert fields["summary"] == "Show monthly revenue"
    assert fields["labels"] == ["frontend"]
    assert fields["priority"] == {"name": "High"}


def test_get_jira_config_reports_unset(client, app_module):
    r = client.get("/jira/config")
    body = r.json()
    assert body["url_set"] is False
    assert body["email_set"] is False
    assert body["token_set"] is False
    assert body["project_set"] is False


def test_set_jira_config_field_by_field(client, app_module):
    for field, value in [
        ("url", "https://example.atlassian.net"),
        ("email", "me@example.com"),
        ("token", "abc"),
        ("project", "DOINGS"),
    ]:
        r = client.post("/jira/config", json={"field": field, "value": value})
        assert r.status_code == 200
    body = client.get("/jira/config").json()
    assert body["url_set"] is True
    assert body["email_set"] is True
    assert body["token_set"] is True
    assert body["project_set"] is True
    # URL + project come back; email + token never do
    assert body["url"] == "https://example.atlassian.net"
    assert body["project"] == "DOINGS"
    assert "token" not in body
    assert "email" not in body


def test_set_jira_config_unknown_field_400s(client, app_module):
    r = client.post("/jira/config", json={"field": "favorite_color", "value": "blue"})
    assert r.status_code == 400


def test_push_requires_full_config(client, app_module):
    app_module.app.state.session.export_draft = {
        "requirements": [_req()],
        "decisions": [],
    }
    r = client.post("/export/push", json={"index": 0})
    assert r.status_code == 400


def test_push_routes_call_create_issue(client, app_module, monkeypatch):
    j: JiraClient = app_module.app.state.jira
    j.set_url("https://example.atlassian.net")
    j.set_email("me@example.com")
    j.set_token("abc")
    j.set_project("DOINGS")

    calls: list[dict] = []

    async def fake_create_issue(*, requirement, decisions, timeout_s=30.0):
        calls.append({"summary": requirement["summary"]})
        return {"key": f"DOINGS-{len(calls)}", "url": f"https://example.atlassian.net/browse/DOINGS-{len(calls)}"}

    monkeypatch.setattr(j, "create_issue", fake_create_issue)

    app_module.app.state.session.export_draft = {
        "requirements": [_req(summary="A"), _req(summary="B")],
        "decisions": [{"summary": "use phi3"}],
    }

    r = client.post("/export/push", json={"index": 1})
    assert r.status_code == 200
    assert r.json()["key"] == "DOINGS-1"

    r = client.post("/export/push-all")
    assert r.status_code == 200
    rows = r.json()["results"]
    assert [row["summary"] for row in rows] == ["A", "B"]
    assert all(row.get("key") for row in rows)


def test_push_all_records_per_item_errors(client, app_module, monkeypatch):
    j: JiraClient = app_module.app.state.jira
    j.set_url("https://example.atlassian.net")
    j.set_email("me@example.com")
    j.set_token("abc")
    j.set_project("DOINGS")

    async def fake_create_issue(*, requirement, decisions, timeout_s=30.0):
        if requirement["summary"] == "B":
            raise RuntimeError("Jira returned 400: bad payload")
        return {"key": "DOINGS-1", "url": "https://example.atlassian.net/browse/DOINGS-1"}

    monkeypatch.setattr(j, "create_issue", fake_create_issue)

    app_module.app.state.session.export_draft = {
        "requirements": [_req(summary="A"), _req(summary="B"), _req(summary="C")],
        "decisions": [],
    }

    r = client.post("/export/push-all")
    rows = r.json()["results"]
    assert rows[0].get("key") and not rows[0].get("error")
    assert rows[1].get("error") and not rows[1].get("key")
    assert rows[2].get("key") and not rows[2].get("error")
