from backend.extractor_prompt import build_messages
from backend.state import Segment


def _seg(text: str, start: float = 0.0, end: float = 1.0, lang: str = "en") -> Segment:
    return Segment(id="seg-001", session_id="s1", text=text, start_s=start, end_s=end, lang=lang)


def test_messages_have_system_and_user():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_prompt_includes_schema_keys():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    sys_text = msgs[0]["content"]
    for key in ("is_requirement", "reasoning", "text", "category", "source_quote", "language", "confidence"):
        assert key in sys_text, f"missing {key} in system prompt"


def test_user_includes_existing_and_window():
    msgs = build_messages(
        window=[_seg("Das System muss schnell sein.", lang="de", end=12.4)],
        existing_texts=["Auth uses OAuth"],
    )
    user_text = msgs[1]["content"]
    assert "Auth uses OAuth" in user_text
    assert "Das System muss schnell sein." in user_text
    assert "[DE]" in user_text


def test_user_omits_existing_block_when_empty():
    msgs = build_messages(window=[_seg("hi")], existing_texts=[])
    user_text = msgs[1]["content"]
    assert "EXISTING" not in user_text or "do not duplicate" in user_text.lower()


def test_existing_is_truncated_to_last_10():
    msgs = build_messages(
        window=[_seg("hi")],
        existing_texts=[f"req {i}" for i in range(20)],
    )
    user_text = msgs[1]["content"]
    assert "req 19" in user_text
    assert "req 10" in user_text
    assert "req 9" not in user_text
