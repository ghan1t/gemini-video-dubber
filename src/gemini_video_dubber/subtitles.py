from __future__ import annotations

import re
import textwrap
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
MIN_CAPTION_SECONDS = 1.0
MAX_CAPTION_CHARS = 74
LINE_WIDTH = 38
MAX_GAP_SECONDS = 0.8
PUNCTUATION_ENDINGS = (".", "!", "?", ":", ";", "。", "！", "？")


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _join_text(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    if right[:1] in ",.!?:;%)]}":
        return f"{left}{right}"
    return f"{left} {right}"


def _wrap_caption_text(text: str) -> str:
    wrapped = textwrap.wrap(
        _clean_text(text),
        width=LINE_WIDTH,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if len(wrapped) <= 2:
        return "\n".join(wrapped)
    midpoint = (len(wrapped) + 1) // 2
    return "\n".join(
        [
            _clean_text(" ".join(wrapped[:midpoint])),
            _clean_text(" ".join(wrapped[midpoint:])),
        ]
    )


def _caption_can_absorb(caption: _Caption, next_start: float, next_text: str) -> bool:
    gap = next_start - caption.end
    if gap > MAX_GAP_SECONDS:
        return False
    if (
        caption.text.endswith(PUNCTUATION_ENDINGS)
        and caption.end - caption.start >= MIN_CAPTION_SECONDS
    ):
        return False
    combined_text = _join_text(caption.text, next_text)
    if len(combined_text) > MAX_CAPTION_CHARS:
        return False
    if next_start - caption.start > MAX_CAPTION_SECONDS:
        return False
    return True


def _caption_end(
    start: float,
    next_start: Optional[float],
    translated_audio_duration: float,
) -> float:
    target = start + MAX_CAPTION_SECONDS
    if next_start is not None:
        target = min(target, next_start)
    if translated_audio_duration > 0:
        target = min(target, translated_audio_duration)
    minimum = start + MIN_CAPTION_SECONDS
    if translated_audio_duration > 0:
        minimum = min(minimum, translated_audio_duration)
    return max(target, minimum)


def _normalize_caption_timing(
    captions: list[_Caption],
    translated_audio_duration: float,
) -> list[_Caption]:
    normalized: list[_Caption] = []
    previous_end = 0.0
    for caption in captions:
        start = max(caption.start, previous_end)
        end = max(caption.end, start)
        if end - start < MIN_CAPTION_SECONDS:
            end = start + MIN_CAPTION_SECONDS
        if translated_audio_duration > 0:
            end = min(end, translated_audio_duration)
        if end <= start:
            continue
        normalized.append(_Caption(start, end, caption.text))
        previous_end = end
    return normalized


def transcript_events_to_srt(
    events: list[TranscriptEvent],
    first_input_sent_seconds: float,
    translated_audio_duration: float,
    start_offset_seconds: float = 0.0,
) -> str:
    usable = [event for event in events if _clean_text(event.text)]
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
        text = _clean_text(event.text)
        next_start = timeline_events[index + 1][0] if index + 1 < len(timeline_events) else None
        if captions and _caption_can_absorb(captions[-1], start, text):
            captions[-1].text = _join_text(captions[-1].text, text)
            captions[-1].end = _caption_end(
                captions[-1].start,
                next_start,
                translated_audio_duration,
            )
        else:
            captions.append(
                _Caption(
                    start=start,
                    end=_caption_end(start, next_start, translated_audio_duration),
                    text=text,
                )
            )

    captions = _normalize_caption_timing(captions, translated_audio_duration)

    rows: list[str] = []
    for index, caption in enumerate(captions, start=1):
        rows.extend(
            [
                str(index),
                f"{_srt_timestamp(caption.start)} --> {_srt_timestamp(caption.end)}",
                _wrap_caption_text(caption.text),
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
