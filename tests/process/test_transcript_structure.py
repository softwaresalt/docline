"""Failing harness tests for transcript structure normalization."""

import pytest

from docline.process.transcripts import normalize_transcript_structure
from docline.readers.transcripts import (
    TranscriptMeta,
    TranscriptReadError,
    TranscriptSegment,
)


def _transcript_meta() -> TranscriptMeta:
    return TranscriptMeta(
        segments=[
            TranscriptSegment(
                start_ms=0,
                end_ms=1_000,
                speaker="Alice",
                text="Welcome everyone.",
            ),
            TranscriptSegment(
                start_ms=1_000,
                end_ms=2_000,
                speaker="Bob",
                text="Thanks, Alice.",
            ),
            TranscriptSegment(
                start_ms=2_000,
                end_ms=3_000,
                speaker="Alice",
                text="Agenda is roadmap.",
            ),
        ],
        speakers=["Alice", "Bob"],
        duration_ms=3_000,
    )


def test_normalize_transcript_structure_adds_required_headings() -> None:
    structured = normalize_transcript_structure(_transcript_meta())
    assert "## Speakers" in structured
    assert "## Timeline" in structured
    assert "## Topics" in structured


def test_normalize_transcript_structure_preserves_chronology() -> None:
    structured = normalize_transcript_structure(_transcript_meta())
    assert structured.index("Welcome everyone.") < structured.index("Thanks, Alice.")


def test_normalize_transcript_structure_rejects_malformed_input() -> None:
    malformed = TranscriptMeta(
        segments=[
            TranscriptSegment(
                start_ms=2_000,
                end_ms=1_000,
                speaker="Alice",
                text="Broken timing.",
            ),
        ],
        speakers=["Alice"],
        duration_ms=1_000,
    )
    with pytest.raises(TranscriptReadError):
        normalize_transcript_structure(malformed)
