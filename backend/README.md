# backend — Step 2: FastAPI fan-out

Receives segments from `capture/`, broadcasts them to the React UI over WebSocket,
and POSTs each one to `staging.doings.de/stt` with retry.

## Setup

```bash
/opt/homebrew/bin/python3.14 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

## Run

```bash
# from the repo root
DOINGS_ENDPOINT=http://localhost:8001/stt \
backend/.venv/bin/uvicorn backend.server:app --reload --port 8000
```

By default, the backend posts deliveries to `https://staging.doings.de/stt`.
Override with `DOINGS_ENDPOINT` for local testing.

## Local echo endpoint (for development)

In a second terminal:

```bash
backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001
```

Then set `DOINGS_ENDPOINT=http://localhost:8001/stt`.

## Endpoints

- `POST /segments` — capture posts each finalized segment here
- `WS /ws` — UI subscribes for segment/delivery/state events
- `POST /control/start` — spawns capture subprocess
- `POST /control/stop` — SIGINTs capture subprocess
- `GET /state` — current session state snapshot
- `GET /session/export` — full session as JSON
- `GET /healthz` — liveness probe

## Tests

```bash
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -v
```
