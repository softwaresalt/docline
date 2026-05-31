"""VTT/transcript reader adapter and pre-processing hooks."""

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
    raise NotImplementedError("stub: transcripts.read_vtt not yet implemented")


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
    raise NotImplementedError("stub: transcripts.preprocess_transcript not yet implemented")


def extract_speaker_turns(meta: TranscriptMeta) -> list[tuple[str, list[TranscriptSegment]]]:
    """Group transcript segments by consecutive speaker turn.

    Args:
        meta: Pre-processed transcript metadata.

    Returns:
        A list of ``(speaker, segments)`` tuples where each entry represents
        one uninterrupted turn by the named speaker.  Segments from unknown
        speakers use the empty string ``""`` as the speaker key.
    """
    raise NotImplementedError("stub: transcripts.extract_speaker_turns not yet implemented")


__all__ = [
    "TranscriptMeta",
    "TranscriptReadError",
    "TranscriptSegment",
    "extract_speaker_turns",
    "preprocess_transcript",
    "read_vtt",
]
