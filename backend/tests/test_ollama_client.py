import httpx
import pytest
import respx

from backend.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_chat_returns_assistant_content():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.post("/api/chat").respond(
            200,
            json={"message": {"role": "assistant", "content": '{"requirements": []}'}},
        )
        client = OllamaClient()
        out = await client.chat(messages=[{"role": "user", "content": "x"}], model="phi3")
    assert out == '{"requirements": []}'


@pytest.mark.asyncio
async def test_chat_timeout_raises():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.post("/api/chat").mock(side_effect=httpx.TimeoutException("slow"))
        client = OllamaClient()
        with pytest.raises(httpx.TimeoutException):
            await client.chat(
                messages=[{"role": "user", "content": "x"}],
                model="phi3",
                timeout_s=0.1,
            )


@pytest.mark.asyncio
async def test_health_ok():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").respond(
            200, json={"models": [{"name": "phi3:latest"}, {"name": "mistral:latest"}]}
        )
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "ok"


@pytest.mark.asyncio
async def test_health_no_model():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").respond(200, json={"models": [{"name": "llama3:latest"}]})
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "no_model"


@pytest.mark.asyncio
async def test_health_offline():
    async with respx.mock(base_url="http://localhost:11434") as mock:
        mock.get("/api/tags").mock(side_effect=httpx.ConnectError("nope"))
        client = OllamaClient()
        result = await client.health(model="phi3")
    assert result == "offline"
