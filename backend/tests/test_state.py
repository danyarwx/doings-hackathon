from backend.state import DeliveryStatus, Segment, SessionState


def test_initial_state_is_idle_and_empty():
    state = SessionState()
    assert state.recording_state == "idle"
    assert state.session_id is None
    assert state.segments == []
    assert state.deliveries == {}


def test_add_segment_records_it():
    state = SessionState()
    seg = Segment(id="seg-001", session_id="s1", text="hi", start_s=0.0, end_s=1.0, lang="en")
    state.add_segment(seg)
    assert state.segments == [seg]
    assert state.deliveries["seg-001"] == DeliveryStatus(id="seg-001", status="pending", attempts=0)


def test_update_delivery_sets_status_and_attempts():
    state = SessionState()
    seg = Segment(id="seg-001", session_id="s1", text="hi", start_s=0.0, end_s=1.0, lang="en")
    state.add_segment(seg)
    state.update_delivery("seg-001", status="delivered", attempts=1)
    assert state.deliveries["seg-001"] == DeliveryStatus(id="seg-001", status="delivered", attempts=1)


def test_delivered_count_returns_count_of_delivered():
    state = SessionState()
    for i in range(3):
        sid = f"seg-{i:03d}"
        state.add_segment(Segment(id=sid, session_id="s1", text="x", start_s=0.0, end_s=1.0, lang="en"))
    state.update_delivery("seg-000", status="delivered", attempts=1)
    state.update_delivery("seg-001", status="delivered", attempts=2)
    state.update_delivery("seg-002", status="failed", attempts=3)
    assert state.delivered_count() == 2


def test_reset_clears_segments_and_deliveries():
    state = SessionState()
    state.add_segment(Segment(id="seg-001", session_id="s1", text="x", start_s=0.0, end_s=1.0, lang="en"))
    state.reset(session_id="s2")
    assert state.segments == []
    assert state.deliveries == {}
    assert state.session_id == "s2"


def test_reset_clears_insights_too():
    from backend.insights import Insight
    state = SessionState()
    ins = Insight(
        id="ins-001",
        session_id="s1",
        category="functional",
        text="x",
        original_text="x",
        source_quote="x",
        detail="",
        language="en",
        certainty="explicit",
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    state.insights.append(ins)
    state.reset(session_id="s2")
    assert state.insights == []


def test_initial_state_has_empty_insights():
    state = SessionState()
    assert state.insights == []
