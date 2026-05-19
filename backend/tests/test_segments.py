def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_post_segment_records_it_and_broadcasts(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "state"
        assert first["state"] == "idle"

        payload = {
            "id": "seg-001",
            "session_id": "sess-test",
            "text": "hi",
            "start_s": 0.0,
            "end_s": 1.0,
            "lang": "en",
        }
        r = client.post("/segments", json=payload)
        assert r.status_code == 202

        msg = ws.receive_json()
        assert msg["type"] == "segment"
        assert msg["segment"]["id"] == "seg-001"
        assert msg["segment"]["text"] == "hi"

        msg = ws.receive_json()
        assert msg["type"] == "delivery"
        assert msg["id"] == "seg-001"
        assert msg["status"] == "pending"


def test_get_state_reflects_posted_segments(client):
    payload = {
        "id": "seg-001",
        "session_id": "sess-test",
        "text": "hi",
        "start_s": 0.0,
        "end_s": 1.0,
        "lang": "en",
    }
    client.post("/segments", json=payload)

    r = client.get("/state")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "idle"
    assert body["session_id"] == "sess-test"
    assert body["segment_count"] == 1


def test_export_returns_segments(client):
    payload = {
        "id": "seg-001",
        "session_id": "sess-test",
        "text": "hi",
        "start_s": 0.0,
        "end_s": 1.0,
        "lang": "en",
    }
    client.post("/segments", json=payload)

    r = client.get("/session/export")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "sess-test"
    assert len(body["segments"]) == 1
    assert body["segments"][0]["id"] == "seg-001"
