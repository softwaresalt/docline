"""Transcript processing stubs for normalization and topic segmentation."""

from dataclasses import dataclass

from docline.readers.transcripts import TranscriptMeta, TranscriptReadError, TranscriptSegment


@dataclass
class TranscriptTopicSection:
    """Placeholder topic section emitted by transcript segmentation.

    Attributes:
        heading: Section heading text.
        start_ms: Inclusive section start time in milliseconds.
        end_ms: Inclusive section end time in milliseconds.
        segments: Source transcript segments grouped into the section.
    """

    heading: str
    start_ms: int
    end_ms: int
    segments: list[TranscriptSegment]


def _format_timestamp(milliseconds: int) -> str:
    """Format milliseconds as a compact mm:ss.mmm timestamp.

    Args:
        milliseconds: Timestamp value in milliseconds.

    Returns:
        Formatted timestamp text.
    """
    minutes, remaining_ms = divmod(milliseconds, 60_000)
    seconds, ms = divmod(remaining_ms, 1_000)
    return f"{minutes:02}:{seconds:02}.{ms:03}"


def _derive_topic_heading(text: str) -> str:
    """Derive a compact heading from the first word of a segment.

    Args:
        text: Source segment text.

    Returns:
        Topic heading text.
    """
    if not text.strip():
        return "Topic"
    return text.split()[0].rstrip(".!?,") or "Topic"


def normalize_transcript_structure(transcript: TranscriptMeta) -> str:
    """Normalize transcript content into a structured Markdown scaffold.

    Args:
        transcript: Parsed transcript metadata and segments.

    Returns:
        Structured Markdown transcript content.

    Raises:
        TranscriptReadError: If any segment has invalid timing.
    """
    timeline_lines: list[str] = []
    for segment in transcript.segments:
        if segment.start_ms >= segment.end_ms:
            raise TranscriptReadError("Transcript segment timing must have start_ms < end_ms")
        speaker = segment.speaker or "Unknown"
        timeline_lines.append(
            f"- [{_format_timestamp(segment.start_ms)} - {_format_timestamp(segment.end_ms)}] "
            f"{speaker}: {segment.text}"
        )

    speaker_lines = [f"- {speaker}" for speaker in transcript.speakers] or ["- Unknown"]
    topic_sections = segment_transcript_topics(transcript)
    topic_lines = [
        f"- {section.heading} ({_format_timestamp(section.start_ms)})" for section in topic_sections
    ] or ["- None"]

    sections = [
        "## Speakers",
        *speaker_lines,
        "",
        "## Timeline",
        *timeline_lines,
        "",
        "## Topics",
        *topic_lines,
    ]
    return "\n".join(sections) + "\n"


def segment_transcript_topics(transcript: TranscriptMeta) -> list[TranscriptTopicSection]:
    """Segment transcript content into topic-oriented sections.

    Args:
        transcript: Parsed transcript metadata and segments.

    Returns:
        Topic-oriented transcript sections.
    """
    if not transcript.segments:
        return []

    primary_speaker = (
        transcript.speakers[0] if transcript.speakers else transcript.segments[0].speaker
    )
    sections: list[TranscriptTopicSection] = []

    for segment in transcript.segments:
        starts_new_section = segment.speaker == primary_speaker or not sections
        if starts_new_section:
            sections.append(
                TranscriptTopicSection(
                    heading=_derive_topic_heading(segment.text),
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    segments=[segment],
                )
            )
            continue

        sections[-1].segments.append(segment)

    return sections


__all__ = [
    "TranscriptTopicSection",
    "normalize_transcript_structure",
    "segment_transcript_topics",
]
