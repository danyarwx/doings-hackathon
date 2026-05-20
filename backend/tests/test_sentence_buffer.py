import asyncio
import pytest
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import Segment


def _seg(id_: str, text: str, start: float, end: float, lang: str = "en") -> Segment:
    return Segment(id=id_, session_id="s1", text=text, start_s=start, end_s=end, lang=lang)


@pytest.mark.asyncio
async def test_flush_on_terminal_punctuation():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "The dashboard must show", 0.0, 2.0))
    assert buf.queue.empty()
    await buf.add(_seg("s2", "monthly revenue.", 2.0, 4.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "The dashboard must show monthly revenue."
    assert u.start_s == 0.0
    assert u.end_s == 4.0
    assert u.segment_ids == ["s1", "s2"]
    assert u.lang == "en"


@pytest.mark.asyncio
async def test_flush_on_silence_gap():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "We need German support", 0.0, 2.0))
    # Next segment starts 2.0s later (gap > 1.5)
    await buf.add(_seg("s2", "and a dashboard", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "We need German support"
    assert u.segment_ids == ["s1"]
    # s2 is now the start of a new buffer; no flush yet
    assert buf.queue.empty()


@pytest.mark.asyncio
async def test_flush_on_max_duration():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=5.0)
    await buf.add(_seg("s1", "long monologue starts", 0.0, 2.0))
    await buf.add(_seg("s2", "and keeps going", 2.0, 4.0))
    await buf.add(_seg("s3", "without any breaks", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "long monologue starts and keeps going without any breaks"
    assert u.end_s - u.start_s >= 5.0


@pytest.mark.asyncio
async def test_blank_audio_segment_dropped():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "[BLANK_AUDIO]", 0.0, 2.0))
    await buf.add(_seg("s2", "", 2.0, 4.0))
    await buf.add(_seg("s3", "real content.", 4.0, 6.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "real content."
    assert u.segment_ids == ["s3"]


@pytest.mark.asyncio
async def test_reset_discards_pending():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "partial thought", 0.0, 2.0))
    buf.reset()
    # Adding a new segment after reset should start fresh, no flush
    await buf.add(_seg("s2", "new sentence.", 0.0, 2.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.segment_ids == ["s2"]


@pytest.mark.asyncio
async def test_majority_lang_with_first_on_tie():
    buf = SentenceBuffer()
    await buf.add(_seg("s1", "Wir brauchen", 0.0, 2.0, lang="de"))
    await buf.add(_seg("s2", "support.", 2.0, 4.0, lang="en"))
    # 1 de + 1 en → tie → first wins
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.lang == "de"
