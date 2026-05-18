# capture — Step 1: Terminal Live STT

Mic → whisper.cpp → timestamped paragraphs in the terminal. Fully offline.

## Setup (macOS Apple Silicon)

Requires **Python 3.10+** (pywhispercpp doesn't run on 3.9). On macOS:

```bash
# install Python 3.10+ if you don't have it
brew install python@3.14
```

Create the venv and install dependencies:

```bash
cd /path/to/doings
/opt/homebrew/bin/python3.14 -m venv capture/.venv
capture/.venv/bin/pip install -r capture/requirements.txt
```

First run downloads `ggml-medium` (~769MB) into `capture/models/`.

## Run

From the repo root:

```bash
PYTHONPATH=. capture/.venv/bin/python -m capture.main
```

Speak. Paragraphs appear like:

```
[00:12.4 → 00:18.6] [DE] Das System muss mindestens 500 Nutzer unterstützen. Die Authentifizierung sollte OAuth verwenden.
[00:20.1 → 00:24.0] [EN] We also need an export function for the data.
```

Press Ctrl-C to stop.

## Options

### Model and device

```bash
--model small | medium | large-v3   # whisper model (default: medium)
--device N                          # input device index (default: system mic)
--list-devices                      # print available input devices and exit
```

### Language

```bash
--language de                       # force German (skip auto-detect)
--language en                       # force English
# default: auto-detect per chunk
```

Whisper's auto-detect can be biased toward English on short utterances. Force the language for single-language sessions to get accurate transcripts and language tags.

### Paragraph grouping

Whisper emits short, fragmented segments. By default they're combined into paragraphs that end on silence, language switches, or a duration cap.

```bash
--paragraph-gap-s 1.5               # silence (s) that ends a paragraph (default: 1.5)
--max-paragraph-s 30.0              # max paragraph duration before forced split (default: 30)
--no-paragraphs                     # disable grouping; print one line per raw segment
```

**Latency note:** paragraphs only print once whisper sees the next segment beyond the gap (or on Ctrl-C). Worst-case latency ≈ chunk size (2s) + gap (1.5s) ≈ 4s.

### Audio preprocessing

```bash
--gain-target-dbfs -25.0            # RMS-normalize chunks to this dBFS (default: -25)
--no-normalize                      # disable RMS normalization
--silence-gate-dbfs -45.0           # skip chunks quieter than this (default: -45)
--no-silence-gate                   # disable the silence gate
```

The silence gate prevents whisper from hallucinating fillers like `[sigh]` on quiet background noise. Raise toward `-35` to gate more aggressively; lower toward `-55` if quiet speech gets dropped.

### Vocabulary hints

Bias whisper toward specific terms (product names, acronyms, names):

```bash
--prompt "OAuth 2.0, Telekom, Kubernetes, REST"
--prompt-file vocab.txt             # read prompt from a file (overrides --prompt)
```

## Manual acceptance test

1. Run `PYTHONPATH=. capture/.venv/bin/python -m capture.main --language de`.
2. Wait for `[transcribe] model loaded.` on stderr.
3. Speak: *"Das System muss mindestens fünfhundert Nutzer unterstützen."*
4. Pause ~2 seconds.
5. Speak: *"Die Authentifizierung sollte OAuth verwenden."*
6. Within ~4s of finishing each utterance, a `[DE]` paragraph appears on stdout.
7. Press Ctrl-C. Final summary line (`[main] stopped. transcribed N segments…`) on stderr.

For an English-only run, swap `--language de` for `--language en`. For an auto-detect run (German bias may suffer on short utterances), omit `--language` entirely.

## Tests

```bash
PYTHONPATH=. capture/.venv/bin/pytest capture/tests -v
```

## Troubleshooting

- **`ModuleNotFoundError: No module named 'capture'`** — run from the repo root with `PYTHONPATH=.`.
- **`pywhispercpp.utils:195 ... unsupported operand type(s) for |`** — your venv is Python 3.9. Recreate it with 3.10+ (`brew install python@3.14`, then rebuild the venv).
- **Auto-detect tags German as `[EN]`** — known whisper bias on short chunks. Use `--language de` for German-only sessions.
- **Garbled output / `[sigh]` / `[music]` artifacts** — raise `--silence-gate-dbfs` (e.g. to `-35`) or check mic levels.
- **No transcript output at all** — confirm mic permission was granted; re-check with `--list-devices` and pass `--device N`.
