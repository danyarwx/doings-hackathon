from backend.insights import Insight


def test_insight_minimal_fields():
    ins = Insight(
        id="ins-001",
        session_id="sess-x",
        text="The system must handle 500 concurrent users.",
        original_text="The system must handle 500 concurrent users.",
        source_quote="The system must handle 500 concurrent users.",
        detail="",
        language="en",
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    assert ins.status == "pending"
    assert ins.text.startswith("The system must")


def test_insight_is_frozen():
    ins = Insight(
        id="ins-001",
        session_id="sess-x",
        text="x",
        original_text="x",
        source_quote="x",
        detail="",
        language="en",
        status="pending",
        created_at_iso="2026-05-19T00:00:00Z",
    )
    import dataclasses
    try:
        ins.status = "approved"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Insight should be frozen")
