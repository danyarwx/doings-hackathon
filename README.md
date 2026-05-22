# doings — Local Meeting Intelligence

Local meeting assistant. Mic audio → on-device whisper.cpp → live React dashboard + HTTPS POST to `staging.doings.de/stt` + a post-meeting LLM pass that produces Jira-ready user stories you can push to a real Jira project. Fully offline STT; audio never leaves the device.

See [voicespec-prd-v3.md](voicespec-prd-v3.md) for the full PRD and [CLAUDE.md](CLAUDE.md) for the engineering brief.

## Repo layout

```
doings/
├── capture/   Python: mic → VAD chunker → whisper.cpp (pywhispercpp) → POST /segments
├── backend/   FastAPI: WS fan-out, SentenceBuffer, ExtractorWorker, LLMRouter, JiraClient
├── ui/        React + Vite + TS + Tailwind: dark dashboard, pill nav, Export view
└── docs/      design specs and implementation plans
```

## Requirements

- macOS Apple Silicon (recommended) — Metal-accelerated whisper.cpp
- **Python 3.10+** (pywhispercpp won't work on 3.9). Tested on 3.14 from Homebrew: `brew install python@3.14`
- **Node 18+** for the UI
- **Ollama** (for live AI insights and the export pass with local models): `brew install ollama`. Then `ollama serve` and `ollama pull phi3`. Skip if you don't want AI insights — capture + transcript + delivery still work.
- *(Optional)* OpenAI and/or Anthropic API key if you want to A/B against cloud models.
- *(Optional, for Step 4 push)* Jira Cloud site + API token. Free tier is fine.

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

The whisper model (`ggml-medium`, ~769 MB) downloads automatically on first capture run into `capture/models/`.

---

## Quick start (TL;DR)

Four terminals, all from the repo root unless noted.

```bash
# Terminal 0 — Ollama (AI insights)
ollama pull phi3            # one-time, ~2.4GB
ollama serve

# Terminal 1 — echo (stand-in for staging.doings.de)
PYTHONPATH=. backend/.venv/bin/uvicorn backend.echo_endpoint:app --port 8001

# Terminal 2 — backend
OLLAMA_MODEL=phi3 DOINGS_ENDPOINT=http://localhost:8001/stt \
  PYTHONPATH=. backend/.venv/bin/uvicorn backend.server:app --reload --port 8000

# Terminal 3 — UI
cd ui && npm run dev
```

Open **http://localhost:5173**, click ▶ Start, allow mic permission, speak. Skip Terminal 0 if you don't care about AI insights — everything else still works.

---

## Running the dashboard

The full stack is **three required processes + Ollama for AI insights**, each in its own terminal. Keep them all running for the demo.

### Terminal 0 — Ollama (optional, enables AI insights)

```bash
ollama serve
```

In another shell (one-time per model):

```bash
ollama pull phi3              # default — fast (~2.4GB)
# Optional alternatives for A/B testing (all live-swappable from the nav):
ollama pull phi4-mini:3.8b    # newer phi, slightly stronger (~2.5GB)
ollama pull mistral           # stronger German (~4GB)
ollama pull llama3.1          # strong reasoning (~5GB)
ollama pull qwen3:8b          # newest qwen, multilingual incl. German (~5.2GB)
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

**Tunable env vars** (everything except `DOINGS_ENDPOINT` is optional):

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `phi3` | Initial LLM. Live-swappable from the nav: `phi3`, `phi4-mini:3.8b`, `mistral`, `llama3.1`, `qwen3:8b`, plus `openai/gpt-4o-mini` and `anthropic/claude-haiku-4-5` if keys are set. |
| `OLLAMA_URL` | `http://localhost:11434` | Override if Ollama runs elsewhere. |
| `OPENAI_API_KEY` | _(unset)_ | Enables the `openai/gpt-4o-mini` cloud model. Can also be set at runtime via the nav. |
| `ANTHROPIC_API_KEY` | _(unset)_ | Enables `anthropic/claude-haiku-4-5`. Can also be set at runtime via the nav. |
| `JIRA_URL` | _(unset)_ | Your Jira Cloud URL, e.g. `https://doings-demo.atlassian.net`. UI form overrides this. |
| `JIRA_EMAIL` | _(unset)_ | Atlassian login email. |
| `JIRA_API_TOKEN` | _(unset)_ | Atlassian API token. Generate at https://id.atlassian.com/manage-profile/security/api-tokens |
| `JIRA_PROJECT` | _(unset)_ | Jira project key (e.g. `KAN`). |
| `BUFFER_MAX_SILENCE_S` | `1.5` | Silence gap (s) that flushes the sentence buffer. |
| `BUFFER_MAX_DURATION_S` | `20.0` | Hard buffer-flush duration (s). |
| `EXTRACTOR_MIN_TEXT_LEN` | `30` | Minimum chars for an extracted requirement. |
| `EXTRACTOR_VERB_GATE` | `true` | Require a modal/intent verb in the extracted text. |
| `EXTRACTOR_QUOTE_MATCH_RATIO` | `0.6` | Fuzziness for `source_quote` ↔ focus utterance. Also accepts any 5-word overlap. |
| `EXTRACTOR_DEDUPE_RATIO` | `0.85` | Fuzzy similarity above which a candidate is treated as a duplicate. |
| `DOINGS_ENDPOINT` | `https://staging.doings.de/stt` | Per-segment delivery target. |

### Terminal 3 — UI (Vite dev server)

```bash
cd /path/to/doings/ui
npm run dev
```

Open **http://localhost:5173** in a browser.

### Using the dashboard

1. **Wait for the WebSocket to connect** — the AI Insights badge turns gray ("Unknown") instead of pink ("Offline"). Top of the page is the pill nav.
2. **(Optional) Set your meeting vocabulary** — click **Vocabulary** in the nav, type domain jargon, acronyms, names (comma-separated is fine), and **Save**. Whisper picks this up as a `--prompt` hint on the next ▶ Start.
3. **(Optional) Pick a model** — the chip in the nav opens a dropdown with local + cloud entries. Cloud entries are disabled until you save the matching API key in the same drawer. Swap any time; the backend pre-warms the new model and shows a pulsing cyan dot ("Loading model…") until it's hot.
4. **Click ▶ Start** — backend spawns `capture/` as a subprocess; timer starts.
   - On the first run, macOS will prompt for microphone permission. Allow it.
   - On the first run, whisper downloads its model.
5. **Speak.** Capture uses a VAD state machine — it watches your RMS volume, starts recording when you speak, and cuts a chunk at the next natural silence (0.5s default). The **Live Transcript** panel shows `[mm:ss.s] [DE/EN]` lines per cut chunk. Language auto-detects per chunk (DE ↔ EN code-switching works).
6. **AI Insights** appear after each natural pause or every 20s. Each card shows the requirement text, an LLM-written one-line **detail** in gray, and **Approve / Edit / Decline** controls. Click **▸ Show source** to reveal the verbatim quote. While the LLM is working, the panel shows a bouncing isometric loader ("Thinking…").
7. **History** lives in the nav — click to browse past sessions; clicking one swaps the transcript panel into a read-only past-session view.
8. **Click ■ Stop** — sends SIGINT to the capture subprocess. The Export tab in the nav lights up.

### The Export pass (Step 4)

After Stop, with at least one approved insight:

1. Click **Export** in the nav. The dashboard switches to the Export view.
2. Click the big **Generate** button. A gooey blob loader runs while the LLM produces a Jira-ready JSON document: user stories with Given/When/Then + acceptance criteria + INVEST validation, plus a list of meeting decisions.
3. **Everything is editable inline.** Issue type, priority, story points, INVEST letters (click to toggle), Given/When/Then, acceptance criteria (add/remove rows), labels (Enter to add, X to remove), summary. Changes autosave back to the backend after 500ms idle.
4. **Push to Jira:**
   - Expand the **Jira connection** drawer at the top of the export view.
   - Paste your Jira site URL, email, API token, and project key (one at a time, each has a Save button). Token + email are write-only; site URL + project echo back.
   - Click **Push to Jira** on a card to create a single issue, or **Push all to Jira** in the header to fire them sequentially. Each card shows the resulting key (e.g. `KAN-12`) with an external-link icon, or the error message inline if it fails.
5. **Download JSON** dumps the current draft as a file in case you want to push it somewhere other than Jira.

Issues land in Jira with **meeting decisions pinned at the top of every issue's description**, then the user story, AC list, and INVEST checklist — all as proper headings + bullet lists via Atlassian Document Format.

### Running capture standalone (no UI)

If you just want a terminal transcript without the dashboard:

```bash
PYTHONPATH=. capture/.venv/bin/python -m capture.main
```

All capture flags (`--model`, `--language`, `--prompt`, `--silence-gate-dbfs`, `--vad-threshold`, `--vad-silence`, `--vad-max-duration`, …) work in both modes.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header shows "Backend offline" (pink dot) | Backend (terminal 2) isn't running on port 8000. Start it. The UI will auto-reconnect. |
| `▶ Start` clicked but nothing happens; backend logs `FileNotFoundError` | The capture venv isn't built. Run `capture/.venv/bin/pip install -r capture/requirements.txt`. |
| Delivery icons stuck on `⟳` then flip to `✗` | `DOINGS_ENDPOINT` points at a dead URL. Match it to whatever port terminal 1 is on. |
| German speech comes back as English text | Almost always fixed already — if it recurs, force the language via the bottom-toolbar DE button. Reason: Whisper's auto-detect can mis-pick on very short or noisy audio. |
| `pywhispercpp` import errors / `unsupported operand type(s) for |` | Your venv is Python 3.9. Recreate it with 3.10+. |
| Port 8000 or 8001 already in use | Pick another port. Backend port is `--port` on uvicorn; UI proxy targets `localhost:8000` so keep the backend on 8000 (or update `ui/vite.config.ts`). |
| `npm run dev` shows `vite] ws proxy socket error: EPIPE` | Harmless dev-mode log when the WS upstream closes. The hook reconnects automatically. |
| AI insights panel says "AI offline" | `ollama serve` isn't running. Start it; the panel reconnects within ~5s of the next utterance. |
| AI insights panel says "Model not installed" | Run `ollama pull <model>` for whatever the picker shows as active. |
| Insights are too few / too many | Tune `EXTRACTOR_MIN_TEXT_LEN` (default `30`) or `EXTRACTOR_VERB_GATE` (default `true`). Lower min length or disable the verb gate → more pass through. Restart backend after env changes. |
| Insights are wrong language or hallucinated | Switch model from the top-nav picker (no restart needed). `mistral` or `qwen3:8b` for German, `llama3.1` / `phi4-mini` / `openai/gpt-4o-mini` for stronger reasoning. |
| Switching to qwen3:8b takes forever the first time | Expected — 8B model cold-load can be 60–120s. The Insights badge shows a pulsing cyan "Loading model…" while it happens. Pre-warm completes in the background. |
| Jira push: `400 The target project doesn't exist…` | Project key typo (case-sensitive) or `JIRA_URL` points at a different Atlassian site. Verify both by opening any issue in Jira and reading the URL. |
| Jira push: `401 Unauthorized` | You pasted your Atlassian password instead of an API token. Generate one at https://id.atlassian.com/manage-profile/security/api-tokens . |

---

## Tests

```bash
PYTHONPATH=. capture/.venv/bin/pytest capture/tests -q          # 28 tests
PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q          # 90 tests
cd ui && npx tsc --noEmit                                       # UI type check
```

No automated UI tests yet — manual acceptance is the contract.

---

## Build order

The project shipped in four sequential roadmap steps. **Each step works end-to-end on its own.**

1. **Terminal Live STT** ✅ — mic → terminal lines (`capture/`)
2. **Beautiful Web UI** ✅ — FastAPI + React dashboard + delivery + history (`backend/`, `ui/`)
3. **Local LLM Analysis** ✅ — VAD-driven capture, `SentenceBuffer` aggregator, event-driven `ExtractorWorker` with a FOCUS+CONTEXT prompt, gated filter (length / verb / fuzzy quote match / fuzzy dedupe), Approve / Edit / Decline cards. Live model swap (local + optional cloud), vocabulary hints from the top nav.
4. **Requirements & Tickets** ✅ — post-meeting LLM pass over approved cards + full transcript → Jira-ready JSON (user stories with Given/When/Then, acceptance criteria, INVEST validation, decisions). Fully editable Export view with autosave; per-card and Push-all to Jira Cloud via REST v3 (ADF descriptions, decisions pinned at the top of every issue).
