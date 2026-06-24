from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from gemini_video_dubber import media


def test_ffprobe_parsing_identifies_duration_and_audio_streams() -> None:
    payload = json.dumps(
        {
            "format": {"duration": "12.5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264"},
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "tags": {"language": "eng"},
                },
            ],
        }
    )

    info = media.parse_ffprobe_json(payload)

    assert info.duration == 12.5
    assert info.video_stream_index == 0
    assert info.audio_streams[0].index == 1
    assert info.original_audio_codec == "aac"


def test_100ms_chunk_size_is_3200_bytes() -> None:
    assert media.PCM_CHUNK_BYTES == 3200


def test_output_filename_timestamp_fallback(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.mp4"
    output_dir = tmp_path
    (tmp_path / "sample_dubbed.mp4").write_bytes(b"exists")

    output = media.output_path_for(
        input_path,
        output_dir,
        now=datetime(2026, 6, 24, 14, 30, 15),
    )

    assert output.name == "sample_dubbed_20260624_143015.mp4"


def test_ffmpeg_command_construction_includes_two_audio_tracks(tmp_path: Path) -> None:
    tools = media.MediaTools(Path("ffmpeg"), Path("ffprobe"))
    command = media.build_remux_command(
        tmp_path / "input.mp4",
        tmp_path / "translated.wav",
        tmp_path / "out.mp4",
        "en",
        "es",
        tools,
    )

    assert command.count("-map") == 3
    assert "0:a:0" in command
    assert "1:a:0" in command
    assert "title=Original" in command
    assert "title=Gemini Dub" in command
