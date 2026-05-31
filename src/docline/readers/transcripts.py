"""VTT/transcript reader adapter and pre-processing hooks."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from docline.schema.models import DoclineError


class TranscriptReadError(DoclineError):
    """Raised when transcript parsing fails."""


@dataclass(frozen=True)
class TranscriptSegment:
    """A single utterance segment from a transcript.

    Attributes:
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds.
        speaker: Speaker identifier, or ``None`` when not present.
        text: The spoken text content.
    """

    start_ms: int
    end_ms: int
    speaker: str | None
    text: str


@dataclass
class TranscriptMeta:
    """Pre-processed transcript metadata for later semantic restructuring.

    Attributes:
        segments: Ordered list of transcript segments.
        speakers: Distinct speaker identifiers encountered, in first-seen order.
        duration_ms: Total transcript duration in milliseconds.
    """

    segments: list[TranscriptSegment] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    duration_ms: int = 0


_TIMING_RE = re.compile(r"^(\S+)\s+-->\s+(\S+)")
_SPEAKER_RE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", re.DOTALL)


def _parse_vtt_timestamp(ts: str) -> int:
    """Convert a WebVTT timestamp string into milliseconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_part = parts[2]
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds_part = parts[1]
    else:
        raise ValueError(f"Invalid WebVTT timestamp: {ts}")

    seconds_text, milliseconds_text = seconds_part.split(".", maxsplit=1)
    seconds = int(seconds_text)
    milliseconds = int(milliseconds_text.ljust(3, "0")[:3])
    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    return (total_seconds * 1000) + milliseconds


def read_vtt(path: Path) -> list[TranscriptSegment]:
    """Parse a WebVTT (``.vtt``) file into an ordered list of segments.

    Args:
        path: Path to the ``.vtt`` file.

    Returns:
        A chronologically ordered list of :class:`TranscriptSegment` objects.

    Raises:
        TranscriptReadError: If the file is not valid WebVTT.
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    if not text.strip().startswith("WEBVTT"):
        raise TranscriptReadError("Not a valid WebVTT file")

    segments: list[TranscriptSegment] = []
    for block in re.split(r"\r?\n\r?\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next(
            (index for index, line in enumerate(lines) if _TIMING_RE.match(line)),
            None,
        )
        if timing_index is None:
            continue

        timing_match = _TIMING_RE.match(lines[timing_index])
        if timing_match is None:
            continue

        cue_text = "\n".join(lines[timing_index + 1 :]).strip()
        if not cue_text:
            continue

        try:
            start_ms = _parse_vtt_timestamp(timing_match.group(1))
            end_ms = _parse_vtt_timestamp(timing_match.group(2))
        except ValueError as err:
            raise TranscriptReadError(f"Invalid WebVTT timing in {path}: {err}") from err

        speaker: str | None = None
        speaker_match = _SPEAKER_RE.match(cue_text)
        if speaker_match is not None:
            speaker = speaker_match.group(1).strip()
            clean_text = speaker_match.group(2).strip()
        else:
            clean_text = cue_text
        clean_text = re.sub(r"</?v(?:\s+[^>]*)?>", "", clean_text).strip()

        segments.append(
            TranscriptSegment(
                start_ms=start_ms,
                end_ms=end_ms,
                speaker=speaker,
                text=clean_text,
            )
        )

    return segments


def preprocess_transcript(segments: list[TranscriptSegment]) -> TranscriptMeta:
    """Apply pre-processing hooks to a segment list and return enriched metadata.

    Pre-processing steps:

    1. Validate chronological ordering; raise on out-of-order segments.
    2. Extract unique speaker identifiers in first-seen order.
    3. Compute total duration from the last segment's ``end_ms``.
    4. Preserve raw utterance boundaries (no merging or splitting).

    Args:
        segments: Ordered transcript segments from :func:`read_vtt` or
            equivalent.

    Returns:
        A :class:`TranscriptMeta` with enriched speaker and time metadata.

    Raises:
        TranscriptReadError: If segments are out of chronological order.
    """
    if not segments:
        return TranscriptMeta()

    for current, following in zip(segments, segments[1:]):
        if current.start_ms > following.start_ms:
            raise TranscriptReadError("Segments are out of chronological order")

    speakers: list[str] = []
    seen_speakers: set[str] = set()
    for segment in segments:
        if segment.speaker is not None and segment.speaker not in seen_speakers:
            seen_speakers.add(segment.speaker)
            speakers.append(segment.speaker)

    return TranscriptMeta(
        segments=segments,
        speakers=speakers,
        duration_ms=segments[-1].end_ms,
    )


def extract_speaker_turns(meta: TranscriptMeta) -> list[tuple[str, list[TranscriptSegment]]]:
    """Group transcript segments by consecutive speaker turn.

    Args:
        meta: Pre-processed transcript metadata.

    Returns:
        A list of ``(speaker, segments)`` tuples where each entry represents
        one uninterrupted turn by the named speaker.  Segments from unknown
        speakers use the empty string ``""`` as the speaker key.
    """
    if not meta.segments:
        return []

    turns: list[tuple[str, list[TranscriptSegment]]] = []
    current_speaker = meta.segments[0].speaker or ""
    current_group: list[TranscriptSegment] = [meta.segments[0]]

    for segment in meta.segments[1:]:
        speaker = segment.speaker or ""
        if speaker == current_speaker:
            current_group.append(segment)
            continue
        turns.append((current_speaker, current_group))
        current_speaker = speaker
        current_group = [segment]

    turns.append((current_speaker, current_group))
    return turns


__all__ = [
    "TranscriptMeta",
    "TranscriptReadError",
    "TranscriptSegment",
    "extract_speaker_turns",
    "preprocess_transcript",
    "read_vtt",
]
