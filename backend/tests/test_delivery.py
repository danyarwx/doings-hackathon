import httpx
import pytest
import respx

from backend.delivery import DeliveryResult, deliver


@pytest.fixture
def segment_payload():
    return {
        "text": "hi",
        "start_ms": 0,
        "end_ms": 1000,
        "lang": "en",
        "session_id": "s1",
    }


@pytest.mark.asyncio
async def test_delivery_success(segment_payload):
    async with respx.mock(base_url="https://staging.doings.de") as mock:
        mock.post("/stt").respond(200)
        result = await deliver(
            payload=segment_payload,
            endpoint="https://staging.doings.de/stt",
            max_attempts=3,
            backoff_seconds=(0.0, 0.0, 0.0),
        )
    assert result == DeliveryResult(status="delivered", attempts=1)


@pytest.mark.asyncio
async def test_delivery_retries_on_5xx_then_succeeds(segment_payload):
    async with respx.mock(base_url="https://staging.doings.de") as mock:
        mock.post("/stt").mock(side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200),
        ])
        result = await deliver(
            payload=segment_payload,
            endpoint="https://staging.doings.de/stt",
            max_attempts=3,
            backoff_seconds=(0.0, 0.0, 0.0),
        )
    assert result == DeliveryResult(status="delivered", attempts=3)


@pytest.mark.asyncio
async def test_delivery_fails_after_max_5xx(segment_payload):
    async with respx.mock(base_url="https://staging.doings.de") as mock:
        mock.post("/stt").respond(500)
        result = await deliver(
            payload=segment_payload,
            endpoint="https://staging.doings.de/stt",
            max_attempts=3,
            backoff_seconds=(0.0, 0.0, 0.0),
        )
    assert result == DeliveryResult(status="failed", attempts=3)


@pytest.mark.asyncio
async def test_delivery_fails_immediately_on_4xx(segment_payload):
    async with respx.mock(base_url="https://staging.doings.de") as mock:
        mock.post("/stt").respond(400)
        result = await deliver(
            payload=segment_payload,
            endpoint="https://staging.doings.de/stt",
            max_attempts=3,
            backoff_seconds=(0.0, 0.0, 0.0),
        )
    assert result == DeliveryResult(status="failed", attempts=1)


@pytest.mark.asyncio
async def test_delivery_retries_on_network_error_then_fails(segment_payload):
    async with respx.mock(base_url="https://staging.doings.de") as mock:
        mock.post("/stt").mock(side_effect=httpx.ConnectError("boom"))
        result = await deliver(
            payload=segment_payload,
            endpoint="https://staging.doings.de/stt",
            max_attempts=3,
            backoff_seconds=(0.0, 0.0, 0.0),
        )
    assert result == DeliveryResult(status="failed", attempts=3)
