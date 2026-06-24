from __future__ import annotations

from pathlib import Path

from gemini_video_dubber.subtitles import TranscriptEvent, transcript_events_to_srt, write_srt


def test_transcript_events_convert_to_valid_srt() -> None:
    content = transcript_events_to_srt(
        [
            TranscriptEvent("Hola", 1.0, "es"),
            TranscriptEvent("mundo", 2.5, "es"),
        ],
        first_input_sent_seconds=0.5,
        translated_audio_duration=5.0,
    )

    assert "1\n00:00:00,500 --> 00:00:02,000\nHola" in content
    assert "2\n00:00:02,000 --> 00:00:05,000\nmundo" in content


def test_first_caption_clamps_to_zero_and_final_end_is_valid() -> None:
    content = transcript_events_to_srt(
        [TranscriptEvent("Early", 0.1, "es")],
        first_input_sent_seconds=1.0,
        translated_audio_duration=1.2,
    )

    assert "00:00:00,000 --> 00:00:01,200" in content


def test_empty_transcripts_are_noop(tmp_path: Path) -> None:
    output = tmp_path / "empty.srt"

    written = write_srt([], output, first_input_sent_seconds=0.0, translated_audio_duration=0.0)

    assert written is False
    assert not output.exists()
