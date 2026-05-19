from backend.extractor_filter import FilterConfig, FilterResult, filter_candidates
from backend.state import Segment


def _seg(text: str, lang: str = "en") -> Segment:
    return Segment(id="seg-001", session_id="s1", text=text, start_s=0.0, end_s=1.0, lang=lang)


WINDOW = [_seg("The system must handle 500 concurrent users."), _seg("Auth should use OAuth 2.0.")]
CFG = FilterConfig()


def _cand(**overrides) -> dict:
    base = {
        "is_requirement": True,
        "reasoning": "modal verb 'must' + system constraint",
        "text": "The system must handle 500 concurrent users.",
        "category": "non_functional",
        "source_quote": "The system must handle 500 concurrent users.",
        "language": "en",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_clean_candidate_passes():
    out = filter_candidates([_cand()], window=WINDOW, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1
    assert out.dropped == []


def test_gate1_is_requirement_false_drops():
    out = filter_candidates([_cand(is_requirement=False)], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "is_requirement"


def test_gate2_low_confidence_drops():
    out = filter_candidates([_cand(confidence=0.4)], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "confidence"


def test_gate2_confidence_floor_env_tunable():
    relaxed = FilterConfig(confidence_floor=0.3)
    out = filter_candidates([_cand(confidence=0.4)], window=WINDOW, existing_texts=[], cfg=relaxed)
    assert len(out.kept) == 1


def test_gate3_hallucinated_quote_drops():
    out = filter_candidates(
        [_cand(source_quote="This sentence is nowhere in the transcript at all.")],
        window=WINDOW,
        existing_texts=[],
        cfg=CFG,
    )
    assert out.kept == []
    assert out.dropped[0].gate == "source_quote"


def test_gate3_paraphrased_quote_close_enough_passes():
    # Minor punctuation diff is fine
    out = filter_candidates(
        [_cand(source_quote="the system must handle 500 concurrent users")],
        window=WINDOW,
        existing_texts=[],
        cfg=CFG,
    )
    assert len(out.kept) == 1


def test_gate3_can_be_disabled():
    relaxed = FilterConfig(require_source_quote=False)
    out = filter_candidates(
        [_cand(source_quote="anything goes")],
        window=WINDOW,
        existing_texts=[],
        cfg=relaxed,
    )
    assert len(out.kept) == 1


def test_gate4_exact_dedup_drops():
    out = filter_candidates(
        [_cand()],
        window=WINDOW,
        existing_texts=["The system must handle 500 concurrent users."],
        cfg=CFG,
    )
    assert out.kept == []
    assert out.dropped[0].gate == "dedup"


def test_gate4_dedup_case_insensitive():
    out = filter_candidates(
        [_cand()],
        window=WINDOW,
        existing_texts=["the SYSTEM must handle 500 concurrent users."],
        cfg=CFG,
    )
    assert out.kept == []


def test_gate5_invalid_category_drops():
    out = filter_candidates([_cand(category="bogus")], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "schema"


def test_gate5_empty_text_drops():
    out = filter_candidates([_cand(text="   ")], window=WINDOW, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "schema"


def test_filter_result_kept_loses_reasoning_and_is_requirement():
    out = filter_candidates([_cand()], window=WINDOW, existing_texts=[], cfg=CFG)
    kept = out.kept[0]
    assert "reasoning" not in kept
    assert "is_requirement" not in kept
