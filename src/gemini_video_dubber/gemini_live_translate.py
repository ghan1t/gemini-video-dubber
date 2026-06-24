from __future__ import annotations

import asyncio
import base64
import binascii
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

from . import media
from .subtitles import TranscriptEvent

MODEL = "gemini-3.5-live-translate-preview"
ProgressCallback = Callable[[str, Optional[float], str], Awaitable[None]]


class GeminiTranslationError(RuntimeError):
    pass


@dataclass
class TranslationResult:
    pcm_path: Path
    first_input_sent_seconds: float
    first_output_received_seconds: float
    output_audio_duration: float
    input_transcripts: list[TranscriptEvent] = field(default_factory=list)
    output_transcripts: list[TranscriptEvent] = field(default_factory=list)
    detected_source_mismatch: Optional[str] = None


def _language_code(transcription: object) -> Optional[str]:
    value = getattr(transcription, "language_code", None)
    if value is None:
        value = getattr(transcription, "languageCode", None)
    return value


def _transcript_text(transcription: object) -> str:
    return str(getattr(transcription, "text", "") or "")


def _audio_payload_bytes(data: object) -> bytes:
    if isinstance(data, bytes):
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError:
            return data
        try:
            decoded = base64.b64decode(text, validate=True)
        except binascii.Error:
            return data
        return decoded or data
    if isinstance(data, str):
        try:
            return base64.b64decode(data, validate=True)
        except binascii.Error:
            return data.encode("utf-8")
    return bytes(data)


async def translate_audio_stream(
    input_path: Path,
    tools: media.MediaTools,
    target_language_code: str,
    selected_source_language_code: str,
    api_key: str,
    output_pcm_path: Path,
    duration_seconds: float,
    cancel_event: asyncio.Event,
    progress: ProgressCallback,
) -> TranslationResult:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiTranslationError(
            "google-genai is not installed. Install requirements-dev.txt first."
        ) from exc

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        translation_config=types.TranslationConfig(
            target_language_code=target_language_code,
            echo_target_language=False,
        ),
    )
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(async_client_args={"ping_timeout": 120}),
    )
    first_input_sent: Optional[float] = None
    first_output_received: Optional[float] = None
    output_bytes = 0
    input_transcripts: list[TranscriptEvent] = []
    output_transcripts: list[TranscriptEvent] = []
    mismatch_counts: dict[str, int] = {}
    mismatch_warning: Optional[str] = None
    started_at = time.monotonic()

    async def send_audio(session: object) -> None:
        nonlocal first_input_sent
        bytes_sent = 0
        async for chunk in media.iter_pcm_chunks(input_path, tools, cancel_event):
            if cancel_event.is_set():
                return
            now = time.monotonic()
            if first_input_sent is None:
                first_input_sent = now
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )
            bytes_sent += len(chunk)
            source_seconds = bytes_sent / (media.PCM_INPUT_RATE * media.PCM_SAMPLE_WIDTH_BYTES)
            percent = (
                min(95.0, (source_seconds / duration_seconds) * 70.0)
                if duration_seconds
                else None
            )
            await progress(
                "extracting_streaming",
                percent,
                f"Streamed {source_seconds:.1f}s of source audio to Gemini.",
            )
            expected_elapsed = source_seconds
            actual_elapsed = time.monotonic() - first_input_sent
            if expected_elapsed > actual_elapsed:
                await asyncio.sleep(expected_elapsed - actual_elapsed)
        if not cancel_event.is_set():
            await session.send_realtime_input(audio_stream_end=True)
            await progress("extracting_streaming", 72.0, "Finished streaming source audio.")

    async def receive_audio(session: object) -> None:
        nonlocal first_output_received, output_bytes, mismatch_warning
        with output_pcm_path.open("wb") as output_file:
            async for response in session.receive():
                if cancel_event.is_set():
                    return
                server_content = getattr(response, "server_content", None)
                if not server_content:
                    continue
                received_at = time.monotonic()
                input_transcription = getattr(server_content, "input_transcription", None)
                if input_transcription:
                    text = _transcript_text(input_transcription)
                    code = _language_code(input_transcription)
                    if text:
                        input_transcripts.append(
                            TranscriptEvent(text, received_at - started_at, code)
                        )
                    if code and code != selected_source_language_code:
                        mismatch_counts[code] = mismatch_counts.get(code, 0) + 1
                        if mismatch_counts[code] >= 3 and mismatch_warning is None:
                            mismatch_warning = (
                                "Warning: selected source language was "
                                f"{selected_source_language_code}, but Gemini detected {code}."
                            )
                            await progress("receiving_translation", None, mismatch_warning)
                output_transcription = getattr(server_content, "output_transcription", None)
                if output_transcription:
                    text = _transcript_text(output_transcription)
                    if text:
                        output_transcripts.append(
                            TranscriptEvent(
                                text,
                                received_at - started_at,
                                _language_code(output_transcription),
                            )
                        )
                model_turn = getattr(server_content, "model_turn", None)
                for part in getattr(model_turn, "parts", []) or []:
                    inline_data = getattr(part, "inline_data", None)
                    data = getattr(inline_data, "data", None)
                    if data:
                        audio_bytes = _audio_payload_bytes(data)
                        if first_output_received is None:
                            first_output_received = received_at
                        output_file.write(audio_bytes)
                        output_bytes += len(audio_bytes)
                        translated_seconds = output_bytes / (
                            media.PCM_OUTPUT_RATE * media.PCM_SAMPLE_WIDTH_BYTES
                        )
                        await progress(
                            "receiving_translation",
                            None,
                            f"Received {translated_seconds:.1f}s of translated audio.",
                        )

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            receiver = asyncio.create_task(receive_audio(session))
            sender = asyncio.create_task(send_audio(session))
            done, pending = await asyncio.wait(
                {sender, receiver},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
            if sender in done and receiver not in done:
                try:
                    await asyncio.wait_for(receiver, timeout=20.0)
                except TimeoutError:
                    receiver.cancel()
                    await asyncio.gather(receiver, return_exceptions=True)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise GeminiTranslationError(f"Gemini Live Translate failed: {exc}") from exc
    finally:
        aclose = getattr(client.aio, "aclose", None)
        if aclose is not None:
            await aclose()

    if cancel_event.is_set():
        raise asyncio.CancelledError
    if not output_pcm_path.exists() or output_pcm_path.stat().st_size == 0:
        raise GeminiTranslationError("Gemini returned no translated audio.")
    if first_input_sent is None or first_output_received is None:
        raise GeminiTranslationError("Gemini session ended before translated audio was received.")

    return TranslationResult(
        pcm_path=output_pcm_path,
        first_input_sent_seconds=first_input_sent - started_at,
        first_output_received_seconds=first_output_received - started_at,
        output_audio_duration=output_bytes / (media.PCM_OUTPUT_RATE * media.PCM_SAMPLE_WIDTH_BYTES),
        input_transcripts=input_transcripts,
        output_transcripts=output_transcripts,
        detected_source_mismatch=mismatch_warning,
    )
