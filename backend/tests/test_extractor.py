import asyncio
import json
import pytest

from backend.extractor import ExtractorWorker
from backend.sentence_buffer import SentenceBuffer, Utterance
from backend.state import SessionState


class StubHub:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def broadcast(self, msg: dict) -> None:
        self.messages.append(msg)


class StubClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, *, messages, model):
        self.calls.append({"messages": messages, "model": model})
        if not self._responses:
            return json.dumps({"requirements": []})
        return self._responses.pop(0)


def _utt(text: str, start: float = 0.0, end: float = 3.0, lang: str = "en") -> Utterance:
    return Utterance(text=text, start_s=start, end_s=end, lang=lang, segment_ids=["s1"])


def _good_candidate(text: str) -> dict:
    return {
        "is_requirement": True,
        "reasoning": "modal + clause",
        "text": text,
        "category": "functional",
        "source_quote": text,
        "language": "en",
        "certainty": "explicit",
    }


@pytest.mark.asyncio
async def test_worker_processes_utterance_and_broadcasts_insight():
    state = SessionState()
    state.recording_state = "recording"
    state.session_id = "sess-x"
    hub = StubHub()
    text = "The dashboard must show monthly revenue for all regions."
    client = StubClient([json.dumps({"requirements": [_good_candidate(text)]})])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt(text))
        # Give the worker time to consume + process.
        await asyncio.sleep(0.05)
        assert any(m["type"] == "insight" for m in hub.messages)
        ins_msg = next(m for m in hub.messages if m["type"] == "insight")
        assert ins_msg["insight"]["certainty"] == "explicit"
        assert "confidence" not in ins_msg["insight"]
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_no_op_when_not_recording():
    state = SessionState()
    state.recording_state = "idle"
    hub = StubHub()
    client = StubClient([json.dumps({"requirements": []})])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt("anything."))
        await asyncio.sleep(0.05)
        assert client.calls == []  # LLM not called
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_passes_context_window():
    state = SessionState()
    state.recording_state = "recording"
    state.session_id = "sess-x"
    hub = StubHub()
    client = StubClient([
        json.dumps({"requirements": []}),
        json.dumps({"requirements": []}),
    ])
    buffer = SentenceBuffer()
    worker = ExtractorWorker(state=state, hub=hub, client=client, model="phi3", buffer=buffer)
    worker.start()
    try:
        await buffer.queue.put(_utt("We're building a CRM.", 0.0, 2.0))
        await asyncio.sleep(0.05)
        await buffer.queue.put(_utt("It must support Salesforce sync.", 2.0, 5.0))
        await asyncio.sleep(0.05)
        # Second call should include first utterance in CONTEXT.
        assert len(client.calls) == 2
        second_user_msg = client.calls[1]["messages"][1]["content"]
        assert "CONTEXT" in second_user_msg
        assert "We're building a CRM." in second_user_msg
    finally:
        await worker.stop()
