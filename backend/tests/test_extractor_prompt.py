from backend.extractor_prompt import SYSTEM_PROMPT, build_messages
from backend.sentence_buffer import Utterance


def _u(text: str, start: float = 0.0, end: float = 2.0, lang: str = "en") -> Utterance:
    return Utterance(text=text, start_s=start, end_s=end, lang=lang, segment_ids=["s1"])


def test_system_prompt_mentions_certainty_and_few_shot():
    assert "certainty" in SYSTEM_PROMPT
    assert "explicit" in SYSTEM_PROMPT
    assert "implied" in SYSTEM_PROMPT
    # Few-shot anchors
    assert "product requirements" in SYSTEM_PROMPT
    assert "must show monthly revenue" in SYSTEM_PROMPT


def test_system_prompt_does_not_mention_confidence():
    assert "confidence" not in SYSTEM_PROMPT.lower()


def test_build_messages_includes_focus_and_context():
    msgs = build_messages(
        focus=_u("The dashboard must show revenue.", 10.0, 13.0),
        context=[_u("We're building a CRM.", 0.0, 3.0)],
        existing_texts=[],
    )
    user = msgs[1]["content"]
    assert "FOCUS" in user
    assert "CONTEXT" in user
    assert "The dashboard must show revenue." in user
    assert "We're building a CRM." in user


def test_build_messages_truncates_existing_to_tail():
    many = [f"req {i}" for i in range(20)]
    msgs = build_messages(focus=_u("focus."), context=[], existing_texts=many)
    user = msgs[1]["content"]
    assert "req 19" in user
    assert "req 9" not in user  # only last 10 included


def test_build_messages_omits_context_block_if_empty():
    msgs = build_messages(focus=_u("focus."), context=[], existing_texts=[])
    user = msgs[1]["content"]
    assert "CONTEXT" not in user
    assert "FOCUS" in user
