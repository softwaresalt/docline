"""Failing harness tests for transcript topic segmentation."""

from docline.process.transcripts import TranscriptTopicSection, segment_transcript_topics
from docline.readers.transcripts import TranscriptMeta, TranscriptSegment


def _transcript_meta() -> TranscriptMeta:
    return TranscriptMeta(
        segments=[
            TranscriptSegment(
                start_ms=0,
                end_ms=1_000,
                speaker="Alice",
                text="Introductions.",
            ),
            TranscriptSegment(
                start_ms=1_000,
                end_ms=2_000,
                speaker="Bob",
                text="Team updates.",
            ),
            TranscriptSegment(
                start_ms=2_000,
                end_ms=3_000,
                speaker="Alice",
                text="Roadmap planning.",
            ),
            TranscriptSegment(
                start_ms=3_000,
                end_ms=4_000,
                speaker="Bob",
                text="Next steps.",
            ),
        ],
        speakers=["Alice", "Bob"],
        duration_ms=4_000,
    )


def test_segment_transcript_topics_groups_expected_sections() -> None:
    sections = segment_transcript_topics(_transcript_meta())
    assert isinstance(sections[0], TranscriptTopicSection)
    assert [section.heading for section in sections] == ["Introductions", "Roadmap"]


def test_segment_transcript_topics_detects_boundaries() -> None:
    sections = segment_transcript_topics(_transcript_meta())
    assert sections[0].end_ms <= sections[1].start_ms
