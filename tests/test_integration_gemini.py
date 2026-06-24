from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from gemini_video_dubber.jobs import DubJob, JobRunner
from gemini_video_dubber.media import discover_media_tools
from gemini_video_dubber.settings import load_api_key


@pytest.mark.integration
def test_translate_old_spice_resource_with_gemini() -> None:
    api_key = load_api_key()
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not set in the environment or .env")

    repo_root = Path(__file__).resolve().parents[1]
    input_path = repo_root / "tests" / "resources" / "Old_Spice-Lecture.mp4"
    output_dir = repo_root / "tests" / "output"
    output_dir.mkdir(exist_ok=True)

    events = []
    job = DubJob(
        input_path=input_path,
        output_dir=output_dir,
        source_language_code="en",
        target_language_code="lv",
        create_subtitles=True,
        api_key=api_key,
        audio_start_offset_seconds=0.0,
    )

    output_path = asyncio.run(JobRunner(events.append).run(job))
    stem = output_path.with_suffix("")

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert stem.with_name(f"{stem.name}_translated_24k_mono.pcm").exists()
    assert stem.with_name(f"{stem.name}_translated_24k_mono.wav").exists()
    assert stem.with_name(f"{stem.name}_translated_subtitles.srt").exists()
    assert output_path.with_suffix(".job_report.json").exists()
    assert any(event.phase == "done" for event in events)

    tools = discover_media_tools()
    probe = subprocess.run(
        [
            str(tools.ffprobe),
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type:stream_disposition=default:"
            "stream_tags=language,handler_name,name",
            "-of",
            "json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    audio_streams = [stream for stream in streams if stream["codec_type"] == "audio"]
    subtitle_streams = [stream for stream in streams if stream["codec_type"] == "subtitle"]

    assert audio_streams[0]["tags"]["language"] == "eng"
    assert audio_streams[0]["tags"]["handler_name"] == "Original - English"
    assert audio_streams[0]["disposition"]["default"] == 0
    assert audio_streams[1]["tags"]["language"] == "lav"
    assert audio_streams[1]["tags"]["handler_name"] == "Latvian - Gemini Dub"
    assert audio_streams[1]["disposition"]["default"] == 1
    assert subtitle_streams[0]["tags"]["language"] == "lav"
    assert subtitle_streams[0]["tags"]["handler_name"] == "Latvian - Gemini Translation"

    subtitle_text = stem.with_name(f"{stem.name}_translated_subtitles.srt").read_text(
        encoding="utf-8"
    )
    assert "00:00:00," in subtitle_text
