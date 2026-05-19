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
