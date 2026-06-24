**Implementation Summary**

This repo implements a Python/Tkinter desktop app that dubs a video using Gemini Live Translate. It extracts the first audio stream with ffmpeg, streams 16 kHz mono PCM to Gemini, receives 24 kHz mono translated PCM, writes a translated WAV, optionally generates approximate subtitles, and remuxes an MP4 with original video, original audio, dubbed audio, and subtitles.

The current integration test uses `tests/resources/Old_Spice-Lecture.mp4`, translates English to Latvian, writes outputs to `tests/output/`, and verifies MP4 stream metadata.

**How To Run**

```bash
source .venv/bin/activate
python -m gemini_video_dubber
```

Run tests:

```bash
pytest -m 'not integration'
pytest tests/test_integration_gemini.py -s
ruff check .
```

The integration test requires `GEMINI_API_KEY` in `.env` or the environment.

**Source Map**

- App entry points:
    - `src/gemini_video_dubber/__main__.py`
    - `src/gemini_video_dubber/app.py`

- GUI:
    - `src/gemini_video_dubber/gui.py`
    - Change file pickers, language dropdowns, API key field, progress/log panel, and `Dub start offset (seconds)` field here.

- Job orchestration:
    - `src/gemini_video_dubber/jobs.py`
    - Main pipeline lives in `JobRunner._run`.
    - Controls validation, ffprobe, Gemini call, WAV writing, subtitle writing, artifact copying, MP4 remux, report JSON.
    - `DubJob.audio_start_offset_seconds` is the signed timing adjustment.

- Gemini Live Translate:
    - `src/gemini_video_dubber/gemini_live_translate.py`
    - Model: `gemini-3.5-live-translate-preview`.
    - Sends 100 ms PCM chunks.
    - Uses `audio_stream_end=True`.
    - Receives raw/base64 audio chunks and transcript events.
    - Websocket ping timeout is set through `types.HttpOptions(async_client_args={"ping_timeout": 120})`.

- Media / ffmpeg:
    - `src/gemini_video_dubber/media.py`
    - ffmpeg/ffprobe discovery checks bundled PyInstaller path, then `vendor/macos` or `vendor/windows`, then `PATH`.
    - `iter_pcm_chunks` extracts 16 kHz PCM.
    - `write_translated_wav` applies signed start offset:
        - positive: leading silence
        - negative: trims translated PCM
    - `build_remux_command` sets:
        - original audio default off
        - dubbed audio default on
        - subtitle default on
        - language metadata and handler names
    - leading silence diagnostics are in `detect_audio_leading_silence` and `detect_pcm_leading_silence`.

- Subtitles:
    - `src/gemini_video_dubber/subtitles.py`
    - Converts Gemini output transcript events to SRT.
    - Groups fragments into readable captions by punctuation, gap, duration, and character limit.
    - Wraps captions to two readable lines.
    - Prevents overlapping subtitle times.

- Languages:
    - `src/gemini_video_dubber/languages.py`
    - UI language list.
    - BCP-47 labels/codes.
    - MP4 3-letter language mapping, e.g. `en -> eng`, `lv -> lav`.

- Settings:
    - `src/gemini_video_dubber/settings.py`
    - Loads `GEMINI_API_KEY` from environment or `.env`.

- Packaging:
    - `pyinstaller/macos.spec`
    - `pyinstaller/windows.spec`
    - `scripts/build_macos.sh`
    - `scripts/build_windows.ps1`
    - Vendor binaries expected under `vendor/macos/ffmpeg`, `vendor/macos/ffprobe`, etc.

**Outputs**

For an input like `Old_Spice-Lecture.mp4`, output files look like:

```text
tests/output/Old_Spice-Lecture_dubbed_YYYYMMDD_HHMMSS.mp4
tests/output/Old_Spice-Lecture_dubbed_YYYYMMDD_HHMMSS.job_report.json
tests/output/Old_Spice-Lecture_dubbed_YYYYMMDD_HHMMSS_translated_24k_mono.pcm
tests/output/Old_Spice-Lecture_dubbed_YYYYMMDD_HHMMSS_translated_24k_mono.wav
tests/output/Old_Spice-Lecture_dubbed_YYYYMMDD_HHMMSS_translated_subtitles.srt
```

**Important Behavior**

- The observed Gemini wall-clock latency is not used as audio delay.
- The report records it as `observed_gemini_latency_seconds` for diagnostics only.
- Actual timing diagnostics include:
    - `original_audio_leading_silence_seconds`
    - `translated_pcm_leading_silence_seconds`
    - `translated_wav_leading_silence_seconds`
    - `subtitle_timeline_origin_seconds`
- The GUI offset is for fine tuning after the corrected baseline. Default should usually be `0.0`.

**Tests**

- Unit tests:
    - `tests/test_media.py`
    - `tests/test_subtitles.py`
    - `tests/test_jobs.py`

- Gemini integration:
    - `tests/test_integration_gemini.py`
    - Uses `tests/resources/Old_Spice-Lecture.mp4`
    - Translates `en` to `lv`
    - Verifies dubbed audio is default and language metadata is correct:
        - original: `eng`, default `0`
        - dub: `lav`, default `1`
        - subtitles: `lav`, default `1`