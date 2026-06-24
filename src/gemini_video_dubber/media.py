from __future__ import annotations

import asyncio
import json
import platform
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

PCM_INPUT_RATE = 16_000
PCM_OUTPUT_RATE = 24_000
PCM_SAMPLE_WIDTH_BYTES = 2
PCM_CHANNELS = 1
PCM_CHUNK_SECONDS = 0.1
PCM_CHUNK_BYTES = int(PCM_INPUT_RATE * PCM_SAMPLE_WIDTH_BYTES * PCM_CHUNK_SECONDS)
SILENCE_DETECT_NOISE = "-35dB"
SILENCE_DETECT_DURATION = "0.05"


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: Path
    ffprobe: Path


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec_name: Optional[str]
    language: Optional[str] = None


@dataclass(frozen=True)
class ProbeInfo:
    duration: float
    video_stream_index: int
    audio_streams: tuple[AudioStreamInfo, ...]
    container_format: str
    original_audio_codec: Optional[str]


def _bundled_executable(name: str) -> Optional[Path]:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    suffix = ".exe" if sys.platform.startswith("win") else ""
    candidate = Path(base) / "bin" / f"{name}{suffix}"
    return candidate if candidate.exists() else None


def _source_vendor_executable(name: str) -> Optional[Path]:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    platform_dir = "windows" if sys.platform.startswith("win") else "macos"
    candidate = Path(__file__).resolve().parents[2] / "vendor" / platform_dir / f"{name}{suffix}"
    if not candidate.exists():
        return None
    if platform_dir == "macos" and platform.machine() == "arm64":
        try:
            file_output = subprocess.run(
                ["file", str(candidate)],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
        except OSError:
            file_output = ""
        if file_output and "arm64" not in file_output:
            return None
    return candidate


def discover_media_tools() -> MediaTools:
    ffmpeg = (
        _bundled_executable("ffmpeg")
        or _source_vendor_executable("ffmpeg")
        or shutil.which("ffmpeg")
    )
    ffprobe = (
        _bundled_executable("ffprobe")
        or _source_vendor_executable("ffprobe")
        or shutil.which("ffprobe")
    )
    if not ffmpeg or not ffprobe:
        missing = []
        if not ffmpeg:
            missing.append("ffmpeg")
        if not ffprobe:
            missing.append("ffprobe")
        raise MediaError(f"Missing required media tool(s): {', '.join(missing)}")
    return MediaTools(Path(ffmpeg), Path(ffprobe))


def parse_ffprobe_json(payload: str) -> ProbeInfo:
    data = json.loads(payload)
    streams = data.get("streams", [])
    format_info = data.get("format", {})
    duration = float(format_info.get("duration") or 0.0)
    container_format = str(format_info.get("format_name") or "")

    video_stream_index = next(
        (int(stream["index"]) for stream in streams if stream.get("codec_type") == "video"),
        -1,
    )
    audio_streams = tuple(
        AudioStreamInfo(
            index=int(stream["index"]),
            codec_name=stream.get("codec_name"),
            language=(stream.get("tags") or {}).get("language"),
        )
        for stream in streams
        if stream.get("codec_type") == "audio"
    )
    if video_stream_index < 0:
        raise MediaError("Input file does not contain a video stream.")
    if not audio_streams:
        raise MediaError("Input file does not contain an audio stream.")
    return ProbeInfo(
        duration=duration,
        video_stream_index=video_stream_index,
        audio_streams=audio_streams,
        container_format=container_format,
        original_audio_codec=audio_streams[0].codec_name,
    )


def probe_input(input_path: Path, tools: MediaTools) -> ProbeInfo:
    command = [
        str(tools.ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise MediaError(result.stderr.strip() or "ffprobe failed to inspect the input file.")
    return parse_ffprobe_json(result.stdout)


def _parse_leading_silence(stderr: str) -> Optional[float]:
    silence_started_at_zero = False
    for line in stderr.splitlines():
        if "silence_start:" in line:
            try:
                silence_start = float(line.rsplit("silence_start:", 1)[1].strip())
            except ValueError:
                continue
            if silence_start <= 0.02:
                silence_started_at_zero = True
            elif not silence_started_at_zero:
                return 0.0
        if silence_started_at_zero and "silence_end:" in line:
            value = line.rsplit("silence_end:", 1)[1].split("|", 1)[0].strip()
            try:
                return float(value)
            except ValueError:
                return None
    return None if silence_started_at_zero else 0.0


def detect_audio_leading_silence(input_path: Path, tools: MediaTools) -> Optional[float]:
    command = [
        str(tools.ffmpeg),
        "-v",
        "info",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-af",
        f"silencedetect=noise={SILENCE_DETECT_NOISE}:d={SILENCE_DETECT_DURATION}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return _parse_leading_silence(result.stderr)


def detect_pcm_leading_silence(
    pcm_path: Path,
    tools: MediaTools,
    sample_rate: int = PCM_OUTPUT_RATE,
) -> Optional[float]:
    command = [
        str(tools.ffmpeg),
        "-v",
        "info",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(PCM_CHANNELS),
        "-i",
        str(pcm_path),
        "-af",
        f"silencedetect=noise={SILENCE_DETECT_NOISE}:d={SILENCE_DETECT_DURATION}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return _parse_leading_silence(result.stderr)


def extract_audio_command(input_path: Path, tools: MediaTools) -> list[str]:
    return [
        str(tools.ffmpeg),
        "-v",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(PCM_INPUT_RATE),
        "-ac",
        str(PCM_CHANNELS),
        "-",
    ]


async def iter_pcm_chunks(
    input_path: Path,
    tools: MediaTools,
    cancel_event: asyncio.Event,
) -> AsyncIterator[bytes]:
    process = await asyncio.create_subprocess_exec(
        *extract_audio_command(input_path, tools),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        while not cancel_event.is_set():
            chunk = await process.stdout.readexactly(PCM_CHUNK_BYTES)
            yield chunk
    except asyncio.IncompleteReadError as exc:
        if exc.partial:
            yield exc.partial
    finally:
        if cancel_event.is_set() and process.returncode is None:
            process.terminate()
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        return_code = await process.wait()
        if return_code != 0 and not cancel_event.is_set():
            raise MediaError(stderr.decode("utf-8", errors="replace").strip() or "ffmpeg failed")


def write_translated_wav(pcm_path: Path, wav_path: Path, start_offset_seconds: float) -> float:
    pcm_bytes = pcm_path.read_bytes()
    silence_frames = max(0, int(start_offset_seconds * PCM_OUTPUT_RATE))
    trim_frames = max(0, int(-start_offset_seconds * PCM_OUTPUT_RATE))
    trim_bytes = trim_frames * PCM_SAMPLE_WIDTH_BYTES * PCM_CHANNELS
    if trim_bytes:
        trim_bytes -= trim_bytes % (PCM_SAMPLE_WIDTH_BYTES * PCM_CHANNELS)
    trimmed_pcm_bytes = pcm_bytes[trim_bytes:]
    silence_bytes = b"\x00" * silence_frames * PCM_SAMPLE_WIDTH_BYTES * PCM_CHANNELS
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(PCM_CHANNELS)
        wav.setsampwidth(PCM_SAMPLE_WIDTH_BYTES)
        wav.setframerate(PCM_OUTPUT_RATE)
        wav.writeframes(silence_bytes + trimmed_pcm_bytes)
    total_frames = silence_frames + len(trimmed_pcm_bytes) // (
        PCM_SAMPLE_WIDTH_BYTES * PCM_CHANNELS
    )
    return total_frames / PCM_OUTPUT_RATE


def output_path_for(input_path: Path, output_dir: Path, now: Optional[datetime] = None) -> Path:
    base = output_dir / f"{input_path.stem}_dubbed.mp4"
    if not base.exists():
        return base
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{input_path.stem}_dubbed_{stamp}.mp4"


def build_remux_command(
    input_path: Path,
    translated_wav: Path,
    output_path: Path,
    source_code: str,
    target_code: str,
    tools: MediaTools,
    subtitle_path: Optional[Path] = None,
    reencode_video: bool = False,
    source_track_title: str = "Original",
    target_track_title: str = "Gemini Dub",
    subtitle_track_title: str = "Gemini Translation",
) -> list[str]:
    command = [
        str(tools.ffmpeg),
        "-y",
        "-i",
        str(input_path),
        "-i",
        str(translated_wav),
    ]
    if subtitle_path is not None:
        command += ["-i", str(subtitle_path)]
    command += [
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-map",
        "1:a:0",
    ]
    if subtitle_path is not None:
        command += ["-map", "2:s:0"]
    command += ["-c:v"]
    command += ["libx264", "-preset", "veryfast", "-crf", "20"] if reencode_video else ["copy"]
    command += [
        "-disposition:a:0",
        "0",
        "-disposition:a:1",
        "default",
        "-c:a",
        "aac",
        "-metadata:s:a:0",
        f"language={source_code}",
        "-metadata:s:a:0",
        f"title={source_track_title}",
        "-metadata:s:a:0",
        f"handler_name={source_track_title}",
        "-metadata:s:a:1",
        f"language={target_code}",
        "-metadata:s:a:1",
        f"title={target_track_title}",
        "-metadata:s:a:1",
        f"handler_name={target_track_title}",
    ]
    if subtitle_path is not None:
        command += [
            "-disposition:s:0",
            "default",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            f"language={target_code}",
            "-metadata:s:s:0",
            f"title={subtitle_track_title}",
            "-metadata:s:s:0",
            f"handler_name={subtitle_track_title}",
        ]
    command += ["-shortest", str(output_path)]
    return command


def remux_video(
    input_path: Path,
    translated_wav: Path,
    output_path: Path,
    source_code: str,
    target_code: str,
    tools: MediaTools,
    subtitle_path: Optional[Path] = None,
    source_track_title: str = "Original",
    target_track_title: str = "Gemini Dub",
    subtitle_track_title: str = "Gemini Translation",
) -> bool:
    for reencode in (False, True):
        command = build_remux_command(
            input_path,
            translated_wav,
            output_path,
            source_code,
            target_code,
            tools,
            subtitle_path,
            reencode_video=reencode,
            source_track_title=source_track_title,
            target_track_title=target_track_title,
            subtitle_track_title=subtitle_track_title,
        )
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return reencode
        if reencode:
            raise MediaError(result.stderr.strip() or "ffmpeg failed to create the output video.")
    return False
