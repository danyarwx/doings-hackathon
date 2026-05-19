import time


def _wait_for_state(client, target, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get("/state").json()
        if body["state"] == target:
            return body
        time.sleep(0.05)
    raise AssertionError(f"state did not reach {target}; last={body}")


def test_start_with_fake_capture_command(client, monkeypatch):
    # Use a long-running shell command as the fake capture process.
    monkeypatch.setenv("CAPTURE_CMD", "sleep 60")

    r = client.post("/control/start")
    assert r.status_code == 200
    _wait_for_state(client, "recording")

    r = client.post("/control/start")
    assert r.status_code == 409  # already recording

    r = client.post("/control/stop")
    assert r.status_code == 200
    _wait_for_state(client, "idle")

    r = client.post("/control/stop")
    assert r.status_code == 409  # already idle


def test_stop_when_idle_returns_409(client):
    r = client.post("/control/stop")
    assert r.status_code == 409
