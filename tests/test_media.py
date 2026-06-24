from __future__ import annotations

import json
import wave
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
    assert "-disposition:a:0" in command
    assert "-disposition:a:1" in command
    assert "default" in command
    assert "title=Original" in command
    assert "title=Gemini Dub" in command


def test_ffmpeg_command_uses_language_track_titles(tmp_path: Path) -> None:
    tools = media.MediaTools(Path("ffmpeg"), Path("ffprobe"))
    command = media.build_remux_command(
        tmp_path / "input.mp4",
        tmp_path / "translated.wav",
        tmp_path / "out.mp4",
        "en",
        "es",
        tools,
        subtitle_path=tmp_path / "translated.srt",
        source_track_title="Original - English",
        target_track_title="Spanish - Gemini Dub",
        subtitle_track_title="Spanish - Gemini Translation",
    )

    assert "title=Original - English" in command
    assert "handler_name=Original - English" in command
    assert "title=Spanish - Gemini Dub" in command
    assert "handler_name=Spanish - Gemini Dub" in command
    assert "title=Spanish - Gemini Translation" in command
    assert "handler_name=Spanish - Gemini Translation" in command


def test_write_translated_wav_negative_offset_trims_audio(tmp_path: Path) -> None:
    pcm_path = tmp_path / "translated.pcm"
    wav_path = tmp_path / "translated.wav"
    pcm_path.write_bytes(b"\x01\x02" * media.PCM_OUTPUT_RATE)

    duration = media.write_translated_wav(pcm_path, wav_path, start_offset_seconds=-0.25)

    with wave.open(str(wav_path), "rb") as wav:
        assert wav.getframerate() == media.PCM_OUTPUT_RATE
    assert wav.getnframes() == int(media.PCM_OUTPUT_RATE * 0.75)
    assert duration == 0.75


def test_parse_leading_silence_detects_initial_silence() -> None:
    stderr = """
    [silencedetect @ 0x123] silence_start: 0
    [silencedetect @ 0x123] silence_end: 1.234 | silence_duration: 1.234
    """

    assert media._parse_leading_silence(stderr) == 1.234


def test_parse_leading_silence_without_initial_silence_returns_zero() -> None:
    stderr = """
    [silencedetect @ 0x123] silence_start: 3.2
    [silencedetect @ 0x123] silence_end: 3.5 | silence_duration: 0.3
    """

    assert media._parse_leading_silence(stderr) == 0.0
