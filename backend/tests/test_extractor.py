import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend.extractor import ExtractorWorker, build_window
from backend.state import Segment, SessionState


def _seg(text: str, end: float, lang: str = "en") -> Segment:
    return Segment(
        id=f"seg-{int(end)}", session_id="s1", text=text, start_s=max(0.0, end - 1.0), end_s=end, lang=lang
    )


def test_build_window_keeps_recent():
    segs = [_seg(f"t{i}", end=float(i)) for i in range(60)]
    window = build_window(segs, window_s=30.0)
    assert window[-1].end_s == 59.0
    assert window[0].end_s >= 29.0


def test_build_window_empty():
    assert build_window([], window_s=30.0) == []


@pytest.mark.asyncio
async def test_tick_skips_when_idle():
    state = SessionState()
    state.recording_state = "idle"
    client = AsyncMock()
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()
    client.chat.assert_not_called()


@pytest.mark.asyncio
async def test_tick_extracts_and_broadcasts():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("The system must handle 500 concurrent users.", end=5.0))

    client = AsyncMock()
    client.chat.return_value = json.dumps({
        "requirements": [{
            "is_requirement": True,
            "reasoning": "modal verb + system constraint",
            "text": "The system must handle 500 concurrent users.",
            "category": "non_functional",
            "source_quote": "The system must handle 500 concurrent users.",
            "language": "en",
            "confidence": 0.9,
        }]
    })
    hub = AsyncMock()

    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    assert len(state.insights) == 1
    assert state.insights[0].category == "non_functional"
    hub.broadcast.assert_called()
    first_call_args = hub.broadcast.call_args_list[0].args[0]
    assert first_call_args["type"] == "insight"


@pytest.mark.asyncio
async def test_tick_drops_low_confidence():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("The system must handle 500 users.", end=5.0))

    client = AsyncMock()
    client.chat.return_value = json.dumps({
        "requirements": [{
            "is_requirement": True,
            "reasoning": "not sure",
            "text": "The system must handle 500 users.",
            "category": "functional",
            "source_quote": "The system must handle 500 users.",
            "language": "en",
            "confidence": 0.3,
        }]
    })
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    assert state.insights == []


@pytest.mark.asyncio
async def test_tick_handles_invalid_json():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    client = AsyncMock()
    client.chat.return_value = "not even json"
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    assert state.insights == []


@pytest.mark.asyncio
async def test_tick_skips_when_inflight():
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    async def slow_chat(*a, **kw):
        await asyncio.sleep(0.1)
        return json.dumps({"requirements": []})

    client = AsyncMock()
    client.chat.side_effect = slow_chat
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")

    t1 = asyncio.create_task(w._tick_once())
    await asyncio.sleep(0.01)
    await w._tick_once()
    await t1

    assert client.chat.call_count == 1


@pytest.mark.asyncio
async def test_tick_broadcasts_ai_status_offline():
    import httpx
    state = SessionState()
    state.session_id = "s1"
    state.recording_state = "recording"
    state.segments.append(_seg("hi", end=1.0))

    client = AsyncMock()
    client.chat.side_effect = httpx.ConnectError("nope")
    hub = AsyncMock()
    w = ExtractorWorker(state=state, hub=hub, client=client, model="phi3")
    await w._tick_once()

    calls = [c.args[0] for c in hub.broadcast.call_args_list]
    assert any(c.get("type") == "ai_status" and c.get("state") == "offline" for c in calls)
