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

    assert "1\n00:00:00,500 --> 00:00:03,500\nHola mundo" in content


def test_first_caption_clamps_to_zero_and_final_end_is_valid() -> None:
    content = transcript_events_to_srt(
        [TranscriptEvent("Early", 0.1, "es")],
        first_input_sent_seconds=1.0,
        translated_audio_duration=1.2,
    )

    assert "00:00:00,000 --> 00:00:01,200" in content


def test_start_offset_shifts_captions_earlier() -> None:
    content = transcript_events_to_srt(
        [TranscriptEvent("Oho.", 4.2, "lv")],
        first_input_sent_seconds=0.0,
        translated_audio_duration=6.0,
        start_offset_seconds=-4.0,
    )

    assert "00:00:00,200 --> 00:00:03,200" in content


def test_sparse_transcripts_do_not_create_long_caption() -> None:
    content = transcript_events_to_srt(
        [
            TranscriptEvent("First", 0.1, "lv"),
            TranscriptEvent("Second", 24.0, "lv"),
        ],
        first_input_sent_seconds=0.0,
        translated_audio_duration=30.0,
    )

    assert "00:00:00,100 --> 00:00:03,100" in content
    assert "00:00:24,000 --> 00:00:27,000" in content


def test_short_fragments_group_into_readable_caption() -> None:
    content = transcript_events_to_srt(
        [
            TranscriptEvent("Kungi,", 0.1, "lv"),
            TranscriptEvent("bārdas spēle mainās.", 0.8, "lv"),
            TranscriptEvent("Ko jūs darāt,", 1.4, "lv"),
            TranscriptEvent("lai izceltos?", 2.0, "lv"),
        ],
        first_input_sent_seconds=0.0,
        translated_audio_duration=8.0,
    )

    assert "Kungi, bārdas spēle mainās." in content
    assert "Ko jūs darāt, lai izceltos?" in content
    assert "2\n" in content


def test_long_caption_wraps_to_two_lines() -> None:
    content = transcript_events_to_srt(
        [
            TranscriptEvent("Šis ir garāks subtitru teksts", 0.1, "lv"),
            TranscriptEvent("kas joprojām tiek attēlots lasāmi.", 0.8, "lv"),
        ],
        first_input_sent_seconds=0.0,
        translated_audio_duration=5.0,
    )

    assert "Šis ir garāks subtitru teksts kas\njoprojām tiek attēlots lasāmi." in content


def test_caption_times_do_not_overlap_after_sorting() -> None:
    content = transcript_events_to_srt(
        [
            TranscriptEvent("A.", 1.0, "lv"),
            TranscriptEvent("B.", 0.8, "lv"),
        ],
        first_input_sent_seconds=0.0,
        translated_audio_duration=5.0,
    )

    assert "00:00:00,800 --> 00:00:01,800" in content
    assert "00:00:01,800 --> 00:00:04,000" in content


def test_empty_transcripts_are_noop(tmp_path: Path) -> None:
    output = tmp_path / "empty.srt"

    written = write_srt([], output, first_input_sent_seconds=0.0, translated_audio_duration=0.0)

    assert written is False
    assert not output.exists()
