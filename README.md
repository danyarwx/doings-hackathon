# doings — Local Meeting Intelligence

Local meeting assistant. Mic audio → on-device whisper.cpp → live React dashboard + HTTPS POST to `staging.doings.de/stt`. Fully offline STT; audio never leaves the device.

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD and [CLAUDE.md](CLAUDE.md) for the engineering brief.

## Repo layout

```
doings/
├── capture/   Python: mic → whisper.cpp (pywhispercpp) → POST /segments to backend
├── backend/   FastAPI: WS fan-out to UI + HTTPS delivery to staging.doings.de + Start/Stop subprocess control
├── ui/        React + Vite + TS + Tailwind: 3-column dark dashboard
└── docs/      design specs and implementation plans
```

## Requirements

- macOS Apple Silicon (recommended) — Metal-accelerated whisper.cpp
- **Python 3.10+** (pywhispercpp won't work on 3.9). Tested on 3.14 from Homebrew: `brew install python@3.14`
- **Node 18+** for the UI
- **Ollama** (for Step 3 AI insights): `brew install ollama` (or download from https://ollama.com). Then `ollama serve` and `ollama pull phi3`. Skip if you don't want AI insights — the rest of the dashboard still works.

## First-time setup

From the repo root:

```bash
# 1. capture (Python STT)
/opt/homebrew/bin/python3.14 -m venv capture/.venv
capture/.venv/bin/pip install -r capture/requirements.txt

# 2. backend (FastAPI)
/opt/homebrew/bin/python3.14 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 3. ui (React)
cd ui && npm install && cd ..
```

The whisper model (`ggml-medium`, ~769MB) downloads automatically on first capture run into `capture/models/`.

---

## Running the dashboard

The full stack is **three required processes + Ollama for AI insights**, each in its own terminal. Keep them all running for the demo.

### Terminal 0 — Ollama (optional, enables AI insights)

```bash
ollama serve
```

In another shell (one-time per model):

```bash
ollama pull phi3        # default — fast (~2.4GB)
# Optional alternatives for A/B testing:
ollama pull mistral     # stronger German (~4GB)
ollama pull llama3.1    # strongest reasoning (~5GB)
```

Skip this terminal if you don't want AI insights — the rest of the dashboard still works (panel will show "AI offline").

### Terminal 1 — local echo endpoint (stand-in for `staging.doings.de`)

```bash
cd /path/to/doings
PYTHONPATH=. backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001
```

Pick a different port if 8001 is busy (e.g. `--port 8002`). Whatever port you choose, pass it as `DOINGS_ENDPOINT` to terminal 2.

### Terminal 2 — backend (FastAPI fan-out)

```bash
cd /path/to/doings
OLLAMA_MODEL=phi3 \
DOINGS_ENDPOINT=http://localhost:8001/stt \
PYTHONPATH=. backend/.venv/bin/uvicorn backend.server:app --reload --port 8000
```

This is what the UI talks to. If you changed the echo port above, change `DOINGS_ENDPOINT` to match.

If you want to point at the real `staging.doings.de/stt` instead, omit `DOINGS_ENDPOINT` (or set it explicitly to `https://staging.doings.de/stt`).

**Tunable env vars:**

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `phi3` | Local LLM for AI insights. Try `mistral`, `llama3.1`, `qwen2.5`. |
| `OLLAMA_URL` | `http://localhost:11434` | Override if Ollama runs elsewhere. |
| `EXTRACTOR_CONFIDENCE_FLOOR` | `0.6` | Filter floor — lower lets more candidates through. |
| `EXTRACTOR_QUOTE_MATCH_RATIO` | `0.75` | Fuzziness for matching `source_quote` against the transcript. |
| `EXTRACTOR_REQUIRE_SOURCE_QUOTE` | `true` | Set `false` to disable hallucination check. |
| `DOINGS_ENDPOINT` | `https://staging.doings.de/stt` | Per-segment delivery target. |

### Terminal 3 — UI (Vite dev server)

```bash
cd /path/to/doings/ui
npm run dev
```

Open **http://localhost:5173** in a browser.

### Using the dashboard

1. **Wait for the WebSocket to connect** — the header dot turns gray ("Idle") instead of pink ("Backend offline").
2. **Click ▶ Start** — backend spawns `capture/` as a subprocess. The dot turns red, the timer starts.
   - On the first run, macOS will prompt for microphone permission. Allow it.
   - On the first run, whisper downloads its model — this can take a minute. Watch terminal 2 for `[transcribe] loading model 'medium'...` followed by `model loaded.`.
3. **Speak.** Within ~3 seconds:
   - The **Live Transcript** panel shows `[mm:ss.s] [DE/EN] text` lines.
   - Terminal 1 (echo) prints each segment as it arrives.
4. **AI Insights** panel fills in within ~5–12s of an utterance (if Ollama is running). Each card has **Approve / Edit / Decline** controls. The header dot shows the AI status (green = ok, amber = model not pulled, pink = offline, gray = unknown).
5. **Click ■ Stop** — sends SIGINT to the capture subprocess. Dot returns to gray.

### Running capture standalone (no UI)

If you just want a terminal transcript without the dashboard:

```bash
PYTHONPATH=. capture/.venv/bin/python -m capture.main
```

All capture flags (`--model`, `--language`, `--prompt`, `--silence-gate-dbfs`, …) work in both modes. See [capture/README.md](capture/README.md) for the full list.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header shows "Backend offline" (pink dot) | Backend (terminal 2) isn't running on port 8000. Start it. The UI will auto-reconnect. |
| `▶ Start` clicked but nothing happens; backend logs `FileNotFoundError` | The capture venv isn't built. Run `capture/.venv/bin/pip install -r capture/requirements.txt`. |
| Delivery icons stuck on `⟳` then flip to `✗` | `DOINGS_ENDPOINT` points at a dead URL. Match it to whatever port terminal 1 is on. |
| Auto-detect tags German as `[EN]` | Known whisper bias on short chunks. Force the language: `CAPTURE_CMD="capture/.venv/bin/python -m capture.main --api-url http://localhost:8000 --language de"` before starting the backend. |
| `pywhispercpp` import errors / `unsupported operand type(s) for |` | Your venv is Python 3.9. Recreate it with 3.10+. |
| Port 8000 or 8001 already in use | Pick another port. Backend port is `--port` on uvicorn; UI proxy targets `localhost:8000` so keep the backend on 8000 (or update `ui/vite.config.ts`). |
| `npm run dev` shows `vite] ws proxy socket error: EPIPE` | Harmless dev-mode log when the WS upstream closes. The hook reconnects automatically. |
| AI insights panel says "AI offline" | `ollama serve` isn't running. Start it; the panel reconnects within ~5s of the next tick. |
| AI insights panel says "Model not installed" | Run `ollama pull phi3` (or whatever `OLLAMA_MODEL` is set to). |
| Insights are too few / too many | Tune `EXTRACTOR_CONFIDENCE_FLOOR` (default `0.6`). Lower → more pass through; higher → stricter. Restart backend after changing env vars. |
| Insights are wrong language or hallucinated | Switch model: `OLLAMA_MODEL=mistral` for German, `llama3.1` for stronger reasoning. Restart backend. |

---

## Tests

```bash
PYTHONPATH=. capture/.venv/bin/pytest capture/tests -q          # 28 tests
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q          # 56 tests
cd ui && npx tsc --noEmit                                       # UI type check
```

No automated UI tests yet — manual acceptance is the contract (see the dashboard flow above).

---

## Build order

The project is built in four sequential roadmap steps. **Each step works end-to-end before the next begins.**

1. **Terminal Live STT** ✅ — mic → terminal lines (`capture/`)
2. **Beautiful Web UI** ✅ — FastAPI + React dashboard + delivery (`backend/`, `ui/`)
3. **Local LLM Analysis** ✅ — Ollama (phi3 default) extracts requirements from a rolling 30s window; Approve / Edit / Decline cards in the Insights panel
4. **Requirements & Tickets** 🔲 — aggregate approved items → structured spec → Doings ingest
