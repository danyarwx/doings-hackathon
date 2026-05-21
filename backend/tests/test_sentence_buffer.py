import asyncio
import pytest
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import Segment


def _seg(id_: str, text: str, start: float, end: float, lang: str = "en") -> Segment:
    return Segment(id=id_, session_id="s1", text=text, start_s=start, end_s=end, lang=lang)


@pytest.mark.asyncio
async def test_punctuation_alone_does_not_flush():
    # Whisper emits "." at every ~2s chunk boundary, so terminal punctuation
    # is not a reliable sentence boundary. Buffer should keep aggregating.
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "The dashboard must show.", 0.0, 2.0))
    await buf.add(_seg("s2", "monthly revenue.", 2.0, 4.0))
    assert buf.queue.empty()


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
async def test_blank_audio_segment_dropped_and_does_not_break_aggregation():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "[BLANK_AUDIO]", 0.0, 2.0))
    await buf.add(_seg("s2", "", 2.0, 4.0))
    await buf.add(_seg("s3", "real content here.", 4.0, 6.0))
    # Force a flush via silence gap.
    await buf.add(_seg("s4", "next utterance.", 10.0, 12.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "real content here."
    assert u.segment_ids == ["s3"]


@pytest.mark.asyncio
async def test_bracketed_noise_flushes_pending():
    # Whisper emits "(crowd chattering)", "(music)", "[typing]" when it hears
    # no speech. Treat those as a pause: flush whatever was pending, drop the
    # noise segment itself.
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "Sales reports should export to CSV.", 0.0, 2.0))
    await buf.add(_seg("s2", "(crowd chattering)", 2.0, 4.0))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.text == "Sales reports should export to CSV."
    assert u.segment_ids == ["s1"]
    # Buffer is now empty; the chatter segment is not the start of a new one.
    assert buf.queue.empty()
    await buf.add(_seg("s3", "next sentence.", 4.0, 6.0))
    assert buf.queue.empty()  # still pending, no flush yet


@pytest.mark.asyncio
async def test_other_noise_descriptors_treated_as_noise():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "The dashboard must show revenue.", 0.0, 2.0))
    # Various whisper noise tags
    await buf.add(_seg("s2", "[music]", 2.0, 4.0))
    u1 = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u1.segment_ids == ["s1"]

    await buf.add(_seg("s3", "Auth uses OAuth.", 4.0, 6.0))
    await buf.add(_seg("s4", "* sighs *", 6.0, 8.0))
    u2 = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u2.segment_ids == ["s3"]


@pytest.mark.asyncio
async def test_reset_discards_pending():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=2.0)
    await buf.add(_seg("s1", "partial thought", 0.0, 1.0))
    buf.reset()
    # New segment after reset; trigger flush via max-duration.
    await buf.add(_seg("s2", "new sentence starts", 0.0, 1.0))
    await buf.add(_seg("s3", "and continues here", 1.0, 2.5))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    assert u.segment_ids == ["s2", "s3"]


@pytest.mark.asyncio
async def test_majority_lang_with_first_on_tie():
    buf = SentenceBuffer(max_silence_s=1.5, max_duration_s=20.0)
    await buf.add(_seg("s1", "Wir brauchen", 0.0, 2.0, lang="de"))
    await buf.add(_seg("s2", "support.", 2.0, 4.0, lang="en"))
    # Force flush via silence gap.
    await buf.add(_seg("s3", "next.", 10.0, 12.0, lang="en"))
    u = await asyncio.wait_for(buf.queue.get(), timeout=0.1)
    # 1 de + 1 en → tie → first wins
    assert u.lang == "de"
