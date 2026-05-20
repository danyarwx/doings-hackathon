from backend.extractor_filter import FilterConfig, filter_candidates
from backend.sentence_buffer import Utterance


GOOD_TEXT = "The dashboard must show monthly revenue for all sales regions."
GOOD_QUOTE = "The dashboard must show monthly revenue for all sales regions."

FOCUS = Utterance(
    text=GOOD_QUOTE,
    start_s=0.0,
    end_s=3.0,
    lang="en",
    segment_ids=["s1"],
)
CFG = FilterConfig()


def _cand(**overrides) -> dict:
    base = {
        "is_requirement": True,
        "reasoning": "modal verb 'must' + complete clause",
        "text": GOOD_TEXT,
        "category": "functional",
        "source_quote": GOOD_QUOTE,
        "language": "en",
        "certainty": "explicit",
    }
    base.update(overrides)
    return base


def test_clean_candidate_passes():
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1
    assert out.dropped == []


def test_is_requirement_false_drops():
    out = filter_candidates([_cand(is_requirement=False)], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "is_requirement"


def test_length_gate_drops_short_fragments():
    short = _cand(text="product requirements", source_quote="product requirements")
    out = filter_candidates([short], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "length"


def test_length_gate_tunable_via_env():
    relaxed = FilterConfig(min_text_len=10)
    short = _cand(text="must show X.", source_quote="must show X.")
    short_focus = Utterance(text="must show X.", start_s=0.0, end_s=1.0, lang="en", segment_ids=["s1"])
    out = filter_candidates([short], focus=short_focus, existing_texts=[], cfg=relaxed)
    assert len(out.kept) == 1


def test_verb_gate_drops_text_without_modal_or_intent_verb():
    nv = _cand(
        text="The product roadmap discussion from yesterday's meeting was useful.",
        source_quote=GOOD_QUOTE,
    )
    out = filter_candidates([nv], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "verb"


def test_verb_gate_accepts_german_modal():
    de_focus = Utterance(
        text="Das Dashboard muss monatliche Einnahmen anzeigen.",
        start_s=0.0, end_s=3.0, lang="de", segment_ids=["s1"],
    )
    de = _cand(
        text="Das Dashboard muss monatliche Einnahmen anzeigen.",
        source_quote="Das Dashboard muss monatliche Einnahmen anzeigen.",
        language="de",
    )
    out = filter_candidates([de], focus=de_focus, existing_texts=[], cfg=CFG)
    assert len(out.kept) == 1


def test_verb_gate_can_be_disabled():
    cfg = FilterConfig(verb_gate=False)
    nv = _cand(
        text="The product roadmap discussion from yesterday's meeting was useful.",
    )
    out = filter_candidates([nv], focus=FOCUS, existing_texts=[], cfg=cfg)
    assert len(out.kept) == 1


def test_source_quote_must_match_focus():
    out = filter_candidates(
        [_cand(source_quote="This sentence is nowhere in the focus utterance.")],
        focus=FOCUS, existing_texts=[], cfg=CFG,
    )
    assert out.dropped[0].gate == "source_quote"


def test_fuzzy_dedupe_drops_near_duplicate():
    existing = ["The dashboard must show monthly revenue for sales regions."]
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=existing, cfg=CFG)
    assert out.kept == []
    assert out.dropped[0].gate == "dedupe"


def test_fuzzy_dedupe_threshold_tunable():
    cfg = FilterConfig(dedupe_ratio=0.99)  # very strict — near-dupes pass
    existing = ["The dashboard must show monthly revenue for sales regions."]
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=existing, cfg=cfg)
    assert len(out.kept) == 1


def test_schema_invalid_certainty_drops():
    out = filter_candidates([_cand(certainty="probably")], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "schema"


def test_schema_invalid_category_drops():
    out = filter_candidates([_cand(category="ux")], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert out.dropped[0].gate == "schema"


def test_internal_fields_stripped_on_survivor():
    out = filter_candidates([_cand()], focus=FOCUS, existing_texts=[], cfg=CFG)
    assert "is_requirement" not in out.kept[0]
    assert "reasoning" not in out.kept[0]
    assert out.kept[0]["certainty"] == "explicit"
