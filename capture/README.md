# capture — Step 1: Terminal Live STT

Mic → whisper.cpp → timestamped lines in the terminal. Fully offline.

## Setup (macOS Apple Silicon)

```bash
cd capture
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

First run downloads the `ggml-medium` model (~769MB) into `capture/models/`.

## Run

```bash
python -m capture.main
```

Speak. Lines appear like:

```
[00:12.4 → 00:15.1] [DE] Das System muss mindestens 500 Nutzer unterstützen.
[00:17.0 → 00:19.3] [EN] Authentication should use OAuth 2.0.
```

Press Ctrl-C to stop.

## Options

```bash
python -m capture.main --model small      # smaller, faster, less accurate
python -m capture.main --model medium     # default
python -m capture.main --device 2         # pick a specific input device
python -m capture.main --list-devices     # print available input devices
```

## Manual acceptance test

1. Run `python -m capture.main`.
2. Wait for `model loaded.` on stderr.
3. Speak: "Das System muss mindestens 500 Nutzer unterstützen."
4. Within ~3s, a line should appear tagged `[DE]` with the German text.
5. Speak: "Authentication should use OAuth 2.0."
6. Within ~3s, a line should appear tagged `[EN]` with the English text.
7. Press Ctrl-C. Final summary line on stderr.

## Tests

```bash
pytest capture/tests
```
