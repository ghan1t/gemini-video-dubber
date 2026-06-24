from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gemini_video_dubber.jobs import DubJob, JobRunner, JobValidationError, validate_job


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
