"""Tests for the post-meeting export pass (Step 4)."""

import json

from backend.insights import Insight
from backend.state import Segment


def _approved_insight(text: str = "Dashboard must show monthly revenue.") -> Insight:
    return Insight(
        id="ins-001",
        session_id="sess-seed",
        text=text,
        original_text=text,
        source_quote=text,
        detail="",
        language="en",
        status="approved",
        created_at_iso="2026-05-21T00:00:00Z",
    )


def _seg(id_: str, text: str, start: float, end: float) -> Segment:
    return Segment(id=id_, session_id="sess-seed", text=text, start_s=start, end_s=end, lang="en")


def test_export_get_reports_not_ready_when_recording(client, app_module):
    s = app_module.app.state.session
    s.recording_state = "recording"
    r = client.get("/export")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert body["draft"] is None


def test_export_get_reports_not_ready_without_approved(client, app_module):
    s = app_module.app.state.session
    s.recording_state = "idle"
    s.insights = []
    r = client.get("/export")
    assert r.json()["ready"] is False


def test_export_get_reports_ready_with_approved(client, app_module):
    s = app_module.app.state.session
    s.recording_state = "idle"
    s.insights.append(_approved_insight())
    s.segments.append(_seg("seg-1", "Dashboard must show monthly revenue.", 0.0, 2.0))
    r = client.get("/export")
    assert r.json()["ready"] is True


def test_generate_rejects_when_not_ready(client, app_module):
    r = client.post("/export/generate")
    assert r.status_code == 409


def test_generate_stores_draft_and_normalizes_shape(client, app_module, monkeypatch):
    s = app_module.app.state.session
    s.recording_state = "idle"
    s.insights.append(_approved_insight())
    s.segments.append(_seg("seg-1", "Dashboard must show monthly revenue.", 0.0, 2.0))

    raw_reply = json.dumps({
        "requirements": [
            {
                "issuetype": "Story",
                "summary": "Show monthly revenue on dashboard",
                "description": {
                    "user_story": {
                        "given": "A sales manager on the dashboard",
                        "when": "They view the home page",
                        "then": "Monthly revenue is displayed",
                    },
                    "acceptance_criteria": ["Revenue rendered as currency", "Updates daily"],
                    "invest_validation": {
                        "independent": True, "negotiable": True, "valuable": True,
                        "estimable": True, "small": True, "testable": True,
                    },
                },
                "priority": "high",
                "labels": ["frontend"],
                "story_points": 3,
            }
        ],
        "decisions": [{"summary": "Use phi3 for live extraction"}],
    })

    async def fake_chat(**_kwargs):
        return raw_reply

    monkeypatch.setattr(app_module.app.state.llm, "chat", fake_chat)

    r = client.post("/export/generate")
    assert r.status_code == 200
    body = r.json()
    assert "requirements" in body["draft"]
    assert "decisions" in body["draft"]
    assert body["draft"]["requirements"][0]["summary"].startswith("Show monthly revenue")
    # Draft is persisted on session state.
    assert app_module.app.state.session.export_draft is not None


def test_generate_returns_502_on_non_json(client, app_module, monkeypatch):
    s = app_module.app.state.session
    s.recording_state = "idle"
    s.insights.append(_approved_insight())
    s.segments.append(_seg("seg-1", "Dashboard must show monthly revenue.", 0.0, 2.0))

    async def fake_chat(**_kwargs):
        return "Sure, here are the requirements: ..."  # not JSON

    monkeypatch.setattr(app_module.app.state.llm, "chat", fake_chat)

    r = client.post("/export/generate")
    assert r.status_code == 502


def test_generate_fills_missing_arrays(client, app_module, monkeypatch):
    s = app_module.app.state.session
    s.recording_state = "idle"
    s.insights.append(_approved_insight())
    s.segments.append(_seg("seg-1", "Dashboard must show monthly revenue.", 0.0, 2.0))

    async def fake_chat(**_kwargs):
        return json.dumps({})  # neither key present

    monkeypatch.setattr(app_module.app.state.llm, "chat", fake_chat)

    r = client.post("/export/generate")
    assert r.status_code == 200
    assert r.json()["draft"]["requirements"] == []
    assert r.json()["draft"]["decisions"] == []


def test_session_reset_clears_export_draft(client, app_module):
    s = app_module.app.state.session
    s.export_draft = {"requirements": [], "decisions": []}
    s.reset(session_id="sess-new")
    assert s.export_draft is None
