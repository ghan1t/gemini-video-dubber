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


MAX_CAPTION_SECONDS = 3.0
MIN_CAPTION_SECONDS = 0.3


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
    start_offset_seconds: float = 0.0,
) -> str:
    usable = [event for event in events if event.text.strip()]
    if not usable:
        return ""

    timeline_events = sorted(
        (
            (
                max(
                    0.0,
                    event.received_at_seconds - first_input_sent_seconds + start_offset_seconds,
                ),
                event,
            )
        for event in usable
        ),
        key=lambda item: item[0],
    )
    captions: list[_Caption] = []
    for index, (start, event) in enumerate(timeline_events):
        if index + 1 < len(timeline_events):
            next_start = timeline_events[index + 1][0]
            end = min(next_start, start + MAX_CAPTION_SECONDS)
        else:
            end = start + MAX_CAPTION_SECONDS
        if translated_audio_duration > 0:
            end = min(end, translated_audio_duration)
        end = max(end, min(start + MIN_CAPTION_SECONDS, translated_audio_duration or end))
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
    start_offset_seconds: float = 0.0,
) -> bool:
    content = transcript_events_to_srt(
        events,
        first_input_sent_seconds,
        translated_audio_duration,
        start_offset_seconds=start_offset_seconds,
    )
    if not content:
        return False
    output_path.write_text(content, encoding="utf-8")
    return True
