from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gemini_video_dubber.gemini_live_translate import TranslationResult
from gemini_video_dubber.jobs import DubJob, JobRunner, JobValidationError, validate_job
from gemini_video_dubber.media import AudioStreamInfo, ProbeInfo
from gemini_video_dubber.subtitles import TranscriptEvent


def _job(tmp_path: Path, api_key: str = "key", source: str = "en", target: str = "es") -> DubJob:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not a real video")
    return DubJob(video, tmp_path, source, target, False, api_key)


def test_missing_api_key_fails_validation(tmp_path: Path) -> None:
    with pytest.raises(JobValidationError, match="Missing Gemini API key"):
        validate_job(_job(tmp_path, api_key=""))


def test_missing_video_path_fails_validation(tmp_path: Path) -> None:
    job = DubJob(tmp_path / "missing.mp4", tmp_path, "en", "es", False, "key")

    with pytest.raises(JobValidationError, match="Video file does not exist"):
        validate_job(job)


def test_identical_source_target_logs_warning(tmp_path: Path) -> None:
    warnings = validate_job(_job(tmp_path, source="en", target="en"))

    assert warnings
    assert "identical" in warnings[0]


def test_cancellation_sets_job_state_to_cancelled(tmp_path: Path) -> None:
    events = []
    runner = JobRunner(events.append)

    async def cancel_run() -> None:
        cancel_event = asyncio.Event()
        cancel_event.set()
        with pytest.raises(asyncio.CancelledError):
            await runner._run(_job(tmp_path), cancel_event)

    asyncio.run(cancel_run())
    assert any(event.phase == "cancelled" for event in events)


def test_job_persists_translated_audio_and_subtitles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_job = _job(tmp_path)
    job = DubJob(
        input_path=base_job.input_path,
        output_dir=base_job.output_dir,
        source_language_code=base_job.source_language_code,
        target_language_code=base_job.target_language_code,
        create_subtitles=True,
        api_key=base_job.api_key,
    )
    events = []

    async def fake_translate_audio_stream(
        input_path,
        tools,
        target_language_code,
        selected_source_language_code,
        api_key,
        output_pcm_path,
        duration_seconds,
        cancel_event,
        progress,
    ):
        output_pcm_path.write_bytes(b"\x01\x02" * 2400)
        return TranslationResult(
            pcm_path=output_pcm_path,
            first_input_sent_seconds=0.0,
            first_output_received_seconds=0.25,
            output_audio_duration=0.1,
            output_transcripts=[TranscriptEvent("Hola", 0.25, "es")],
        )

    def fake_remux_video(*args, **kwargs):
        output_path = args[2]
        output_path.write_bytes(b"mp4")
        return False

    monkeypatch.setattr(
        "gemini_video_dubber.jobs.translate_audio_stream",
        fake_translate_audio_stream,
    )
    monkeypatch.setattr("gemini_video_dubber.jobs.media.discover_media_tools", lambda: object())
    monkeypatch.setattr(
        "gemini_video_dubber.jobs.media.probe_input",
        lambda input_path, tools: ProbeInfo(
            duration=1.0,
            video_stream_index=0,
            audio_streams=(AudioStreamInfo(index=1, codec_name="aac"),),
            container_format="mov,mp4",
            original_audio_codec="aac",
        ),
    )
    monkeypatch.setattr("gemini_video_dubber.jobs.media.remux_video", fake_remux_video)
    monkeypatch.setattr(
        "gemini_video_dubber.jobs.media.detect_audio_leading_silence",
        lambda input_path, tools: 0.0,
    )
    monkeypatch.setattr(
        "gemini_video_dubber.jobs.media.detect_pcm_leading_silence",
        lambda input_path, tools: 0.1,
    )

    output_path = asyncio.run(JobRunner(events.append).run(job))
    stem = output_path.with_suffix("")

    assert output_path.exists()
    assert stem.with_name(f"{stem.name}_translated_24k_mono.pcm").exists()
    assert stem.with_name(f"{stem.name}_translated_24k_mono.wav").exists()
    assert stem.with_name(f"{stem.name}_translated_subtitles.srt").exists()
    assert output_path.with_suffix(".job_report.json").exists()
