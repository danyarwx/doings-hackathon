"""Local stand-in for staging.doings.de/stt during development.

Run with: `backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001`
Then set `DOINGS_ENDPOINT=http://localhost:8001/stt` on the main backend.
"""

from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/stt")
async def stt(request: Request) -> dict:
    body = await request.json()
    print(f"[echo] received: {body}")
    return {"echoed": True}
