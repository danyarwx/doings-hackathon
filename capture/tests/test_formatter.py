from capture.formatter import format_segment
from capture.segment import Segment


def test_german_segment():
    seg = Segment(
        text="Das System muss mindestens 500 Nutzer unterstützen.",
        start_s=12.4,
        end_s=15.1,
        lang="de",
    )
    assert format_segment(seg) == (
        "[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen."
    )


def test_english_segment():
    seg = Segment(text="Authentication should use OAuth 2.0.", start_s=17.0, end_s=19.3, lang="en")
    assert format_segment(seg) == "[00:17.0 → 00:19.3] [EN] Authentication should use OAuth 2.0."


def test_zero_padding():
    seg = Segment(text="hi", start_s=0.4, end_s=3.1, lang="en")
    assert format_segment(seg) == "[00:00.4 → 00:03.1] [EN] hi"


def test_minutes_past_one_hour():
    # Session-relative time keeps growing; we don't wrap at 60 minutes.
    seg = Segment(text="long meeting", start_s=3661.5, end_s=3663.0, lang="en")
    assert format_segment(seg) == "[61:01.5 → 61:03.0] [EN] long meeting"


def test_empty_text_returns_none():
    seg = Segment(text="", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) is None


def test_whitespace_only_text_returns_none():
    seg = Segment(text="   ", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) is None


def test_strips_text():
    seg = Segment(text="  hello  ", start_s=1.0, end_s=2.0, lang="en")
    assert format_segment(seg) == "[00:01.0 → 00:02.0] [EN] hello"
