from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    received_at_seconds: float
    language_code: Optional[str] = None


@dataclass
class _Caption:
    start: float
    end: float
    text: str


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def transcript_events_to_srt(
    events: list[TranscriptEvent],
    first_input_sent_seconds: float,
    translated_audio_duration: float,
) -> str:
    usable = [event for event in events if event.text.strip()]
    if not usable:
        return ""

    starts = [max(0.0, event.received_at_seconds - first_input_sent_seconds) for event in usable]
    captions: list[_Caption] = []
    for index, event in enumerate(usable):
        start = starts[index]
        if index + 1 < len(usable):
            end = max(start + 0.6, starts[index + 1])
        else:
            end = start + 3.0
        if translated_audio_duration > 0:
            end = min(end, translated_audio_duration)
        end = max(end, start + 0.3)
        captions.append(_Caption(start, end, event.text.strip()))

    merged: list[_Caption] = []
    for caption in captions:
        close_to_previous = bool(merged) and caption.start - merged[-1].end <= 0.2
        previous_is_short = bool(merged) and merged[-1].end - merged[-1].start < 0.8
        if close_to_previous and previous_is_short:
            merged[-1].text = f"{merged[-1].text} {caption.text}"
            merged[-1].end = caption.end
        else:
            merged.append(caption)

    rows: list[str] = []
    for index, caption in enumerate(merged, start=1):
        rows.extend(
            [
                str(index),
                f"{_srt_timestamp(caption.start)} --> {_srt_timestamp(caption.end)}",
                caption.text,
                "",
            ]
        )
    return "\n".join(rows)


def write_srt(
    events: list[TranscriptEvent],
    output_path: Path,
    first_input_sent_seconds: float,
    translated_audio_duration: float,
) -> bool:
    content = transcript_events_to_srt(events, first_input_sent_seconds, translated_audio_duration)
    if not content:
        return False
    output_path.write_text(content, encoding="utf-8")
    return True
