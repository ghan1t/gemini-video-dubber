# Gemini Video Dubber

Small Python desktop app that extracts a video's first audio stream, streams it to Gemini Live Translate, and remuxes a dubbed MP4 with:

- original video copied unchanged where possible
- original audio track
- translated Gemini audio track
- optional approximate subtitle track from output transcript events

Gemini Live Translate accepts raw 16-bit PCM mono audio at 16 kHz and returns raw 16-bit PCM mono audio at 24 kHz. Video is processed locally with `ffmpeg`/`ffprobe`.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` on `PATH`, or bundled under `vendor/<platform>/`
- Gemini API key in `GEMINI_API_KEY`, `.env`, or the app's one-time API key field

Dependency versions were checked against current online PyPI JSON metadata on 2026-06-24 and pinned in `requirements.txt` / `requirements-dev.txt`.

## Setup

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env` or enter it in the GUI.

## Run

```bash
python -m gemini_video_dubber
```

When running from source, the app checks `vendor/macos/ffmpeg` and `vendor/macos/ffprobe`
before falling back to `PATH`.

Use the GUI's dub start offset field to tune translated audio timing.
Positive values delay the dub; negative values start it earlier by trimming translated audio.
Approximate subtitle timing is derived separately from Gemini output transcript events
using translated-audio positions plus measured leading silence in the translated PCM.
The job report includes the observed Gemini wall-clock latency for diagnostics, plus
measured leading silence for the original audio, raw translated PCM, final translated WAV,
and subtitle timing preview fields. Use the measured silence values and subtitle timing
fields, not the wall-clock latency, when diagnosing sync.

## Test

```bash
pytest
ruff check .
```

The Gemini integration test uses `tests/resources/TedTalk.mp4`, reads
`GEMINI_API_KEY` from `.env`, and writes persistent outputs to `tests/output/`:

```bash
pytest tests/test_integration_gemini.py -s
```

## Package

macOS builds must be created on macOS:

```bash
scripts/build_macos.sh
```

Windows builds must be created on Windows:

```powershell
scripts\build_windows.ps1
```

Place platform `ffmpeg`/`ffprobe` binaries here before packaging:

- `vendor/macos/ffmpeg`
- `vendor/macos/ffprobe`
- `vendor/windows/ffmpeg.exe`
- `vendor/windows/ffprobe.exe`

Do not package `.env` or API keys.
