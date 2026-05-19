from capture.aggregator import ParagraphAggregator
from capture.segment import Segment


def seg(text: str, start: float, end: float, lang: str = "en") -> Segment:
    return Segment(text=text, start_s=start, end_s=end, lang=lang)


def test_single_segment_flushes_as_one_paragraph():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.add(seg("Hello.", 0.0, 1.0)) == []
    assert agg.flush() == [seg("Hello.", 0.0, 1.0)]


def test_two_close_segments_merge_into_one_paragraph():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.add(seg("Hello.", 0.0, 1.0)) == []
    assert agg.add(seg("World.", 1.5, 2.5)) == []  # gap = 0.5s, below threshold
    paragraphs = agg.flush()
    assert paragraphs == [Segment(text="Hello. World.", start_s=0.0, end_s=2.5, lang="en")]


def test_long_gap_emits_first_paragraph():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.add(seg("First.", 0.0, 1.0)) == []
    emitted = agg.add(seg("Second.", 3.0, 4.0))  # gap = 2.0s, above threshold
    assert emitted == [seg("First.", 0.0, 1.0)]
    assert agg.flush() == [seg("Second.", 3.0, 4.0)]


def test_language_change_splits_paragraphs():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.add(seg("Hello.", 0.0, 1.0, lang="en")) == []
    emitted = agg.add(seg("Hallo.", 1.2, 2.0, lang="de"))  # same time, different lang
    assert emitted == [seg("Hello.", 0.0, 1.0, lang="en")]
    assert agg.flush() == [seg("Hallo.", 1.2, 2.0, lang="de")]


def test_max_paragraph_duration_forces_split():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=5.0)
    assert agg.add(seg("One.", 0.0, 1.0)) == []
    assert agg.add(seg("Two.", 1.5, 2.5)) == []
    # Adding this segment would make paragraph span 0.0 -> 6.0 = 6.0s > 5.0 cap.
    emitted = agg.add(seg("Three.", 5.0, 6.0))
    assert emitted == [Segment(text="One. Two.", start_s=0.0, end_s=2.5, lang="en")]
    assert agg.flush() == [seg("Three.", 5.0, 6.0)]


def test_empty_flush_returns_nothing():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.flush() == []


def test_current_reflects_in_progress_paragraph():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    assert agg.current() is None
    agg.add(seg("Hello.", 0.0, 1.0))
    assert agg.current() == seg("Hello.", 0.0, 1.0)
    agg.add(seg("World.", 1.2, 2.0))
    assert agg.current() == Segment(text="Hello. World.", start_s=0.0, end_s=2.0, lang="en")
    agg.flush()
    assert agg.current() is None


def test_text_is_joined_with_single_space_and_stripped():
    agg = ParagraphAggregator(gap_s=1.5, max_paragraph_s=30.0)
    agg.add(seg("  First  ", 0.0, 1.0))
    agg.add(seg("  second.", 1.2, 2.0))
    assert agg.flush() == [Segment(text="First second.", start_s=0.0, end_s=2.0, lang="en")]
