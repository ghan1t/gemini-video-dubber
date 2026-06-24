from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from . import media
from .gemini_live_translate import GeminiTranslationError, translate_audio_stream
from .languages import label_for_code, mp4_language_for_code
from .subtitles import write_srt


@dataclass(frozen=True)
class DubJob:
    input_path: Path
    output_dir: Path
    source_language_code: str
    target_language_code: str
    create_subtitles: bool
    api_key: str
    audio_start_offset_seconds: float = 0.0


@dataclass(frozen=True)
class JobProgress:
    phase: str
    percent: Optional[float]
    message: str


class JobValidationError(ValueError):
    pass


ProgressSink = Callable[[JobProgress], None]


def validate_job(job: DubJob) -> list[str]:
    warnings: list[str] = []
    if not job.api_key.strip():
        raise JobValidationError("Missing Gemini API key.")
    if not job.input_path.exists() or not job.input_path.is_file():
        raise JobValidationError("Video file does not exist.")
    if not job.output_dir.exists() or not job.output_dir.is_dir():
        raise JobValidationError("Output folder does not exist.")
    if job.source_language_code == job.target_language_code:
        warnings.append(
            "Source and target languages are identical; Gemini may stay silent because echo is off."
        )
    return warnings


class JobRunner:
    def __init__(self, progress_sink: ProgressSink) -> None:
        self._progress_sink = progress_sink
        self._cancel_event: Optional[asyncio.Event] = None

    def cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _emit(self, phase: str, percent: Optional[float], message: str) -> None:
        self._progress_sink(JobProgress(phase, percent, message))

    async def run(self, job: DubJob) -> Path:
        self._cancel_event = asyncio.Event()
        try:
            return await self._run(job, self._cancel_event)
        finally:
            self._cancel_event = None

    async def _progress(self, phase: str, percent: Optional[float], message: str) -> None:
        self._emit(phase, percent, message)

    async def _run(self, job: DubJob, cancel_event: asyncio.Event) -> Path:
        try:
            self._emit("validating", 0.0, "Validating inputs.")
            warnings = validate_job(job)
            for warning in warnings:
                self._emit("validating", None, f"Warning: {warning}")
            if cancel_event.is_set():
                raise asyncio.CancelledError

            tools = media.discover_media_tools()
            self._emit("probing", 5.0, "Probing input media.")
            probe = media.probe_input(job.input_path, tools)
            output_path = media.output_path_for(job.input_path, job.output_dir)
            artifact_stem = output_path.with_suffix("")

            tmp_dir = Path(tempfile.mkdtemp(prefix="gemini_video_dubber_"))
            translated_pcm = tmp_dir / "translated_24k_mono.pcm"
            translated_wav = tmp_dir / "translated_24k_mono.wav"
            subtitle_path = tmp_dir / "translated_subtitles.srt"
            report_path = tmp_dir / "job_report.json"
            try:
                result = await translate_audio_stream(
                    job.input_path,
                    tools,
                    job.target_language_code,
                    job.source_language_code,
                    job.api_key,
                    translated_pcm,
                    probe.duration,
                    cancel_event,
                    self._progress,
                )
                if cancel_event.is_set():
                    raise asyncio.CancelledError

                observed_latency = max(
                    0.0,
                    result.first_output_received_seconds - result.first_input_sent_seconds,
                )
                start_offset = job.audio_start_offset_seconds
                self._emit(
                    "writing_audio",
                    78.0,
                    f"Writing translated WAV with {start_offset:.2f}s start offset.",
                )
                translated_duration = media.write_translated_wav(
                    result.pcm_path,
                    translated_wav,
                    start_offset,
                )
                original_leading_silence = media.detect_audio_leading_silence(
                    job.input_path,
                    tools,
                )
                translated_pcm_leading_silence = media.detect_pcm_leading_silence(
                    result.pcm_path,
                    tools,
                )
                subtitle_timeline_origin = result.first_output_received_seconds - (
                    translated_pcm_leading_silence or 0.0
                )
                translated_wav_leading_silence = media.detect_audio_leading_silence(
                    translated_wav,
                    tools,
                )

                mux_subtitle_path = None
                subtitle_artifact_available = False
                if job.create_subtitles:
                    self._emit("writing_subtitles", 84.0, "Writing approximate subtitle track.")
                    if write_srt(
                        result.output_transcripts,
                        subtitle_path,
                        subtitle_timeline_origin,
                        translated_duration,
                        start_offset_seconds=job.audio_start_offset_seconds,
                    ):
                        mux_subtitle_path = subtitle_path
                        subtitle_artifact_available = True
                    else:
                        subtitle_path.write_text("", encoding="utf-8")
                        subtitle_artifact_available = True
                        self._emit(
                            "writing_subtitles",
                            None,
                            "No transcript text received for SRT.",
                        )

                report = {
                    "input_path": str(job.input_path),
                    "output_path": str(output_path),
                    "source_language_code": job.source_language_code,
                    "target_language_code": job.target_language_code,
                    "create_subtitles": job.create_subtitles,
                    "audio_start_offset_seconds": job.audio_start_offset_seconds,
                    "duration": probe.duration,
                    "leading_silence_seconds": max(0.0, start_offset),
                    "trimmed_translated_audio_seconds": max(0.0, -start_offset),
                    "observed_gemini_latency_seconds": observed_latency,
                    "original_audio_leading_silence_seconds": original_leading_silence,
                    "translated_pcm_leading_silence_seconds": translated_pcm_leading_silence,
                    "translated_wav_leading_silence_seconds": translated_wav_leading_silence,
                    "subtitle_timeline_origin_seconds": subtitle_timeline_origin,
                    "source_language_warning": result.detected_source_mismatch,
                    "input_transcript_count": len(result.input_transcripts),
                    "output_transcript_count": len(result.output_transcripts),
                }
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

                artifact_pcm_path = artifact_stem.with_name(
                    f"{artifact_stem.name}_translated_24k_mono.pcm"
                )
                artifact_wav_path = artifact_stem.with_name(
                    f"{artifact_stem.name}_translated_24k_mono.wav"
                )
                artifact_srt_path = artifact_stem.with_name(
                    f"{artifact_stem.name}_translated_subtitles.srt"
                )
                shutil.copy2(translated_pcm, artifact_pcm_path)
                shutil.copy2(translated_wav, artifact_wav_path)
                if subtitle_artifact_available:
                    shutil.copy2(subtitle_path, artifact_srt_path)

                report["translated_pcm_path"] = str(artifact_pcm_path)
                report["translated_wav_path"] = str(artifact_wav_path)
                report["translated_subtitles_path"] = (
                    str(artifact_srt_path) if subtitle_artifact_available else None
                )
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

                self._emit("muxing", 90.0, "Creating dubbed MP4.")
                source_label = label_for_code(job.source_language_code)
                target_label = label_for_code(job.target_language_code)
                used_video_fallback = media.remux_video(
                    job.input_path,
                    translated_wav,
                    output_path,
                    mp4_language_for_code(job.source_language_code),
                    mp4_language_for_code(job.target_language_code),
                    tools,
                    mux_subtitle_path,
                    source_track_title=f"Original - {source_label}",
                    target_track_title=f"{target_label} - Gemini Dub",
                    subtitle_track_title=f"{target_label} - Gemini Translation",
                )
                if used_video_fallback:
                    self._emit("muxing", None, "Copied video stream failed; used H.264 fallback.")
                shutil.copy2(report_path, output_path.with_suffix(".job_report.json"))
                self._emit("done", 100.0, f"Done: {output_path}")
                return output_path
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except asyncio.CancelledError:
            self._emit("cancelled", None, "Job cancelled.")
            raise
        except (JobValidationError, media.MediaError, GeminiTranslationError) as exc:
            self._emit("failed", None, str(exc))
            raise
        except Exception as exc:
            self._emit("failed", None, f"Unexpected failure: {exc}")
            raise


async def run_job(job: DubJob, progress_sink: ProgressSink) -> Path:
    return await JobRunner(progress_sink).run(job)


def job_to_dict(job: DubJob) -> dict[str, object]:
    data = asdict(job)
    data["input_path"] = str(job.input_path)
    data["output_dir"] = str(job.output_dir)
    data["api_key"] = "***"
    return data
