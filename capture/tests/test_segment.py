from capture.segment import Segment


def test_segment_has_optional_id_and_session_id():
    seg = Segment(text="hi", start_s=0.0, end_s=1.0, lang="en")
    assert seg.id is None
    assert seg.session_id is None


def test_segment_accepts_id_and_session_id():
    seg = Segment(
        text="hi",
        start_s=0.0,
        end_s=1.0,
        lang="en",
        id="seg-001",
        session_id="sess-20260518-090000",
    )
    assert seg.id == "seg-001"
    assert seg.session_id == "sess-20260518-090000"
