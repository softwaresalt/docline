"""Test harness for 003.010-T — Add transcript preprocessing hooks.

Acceptance criteria:
- preprocess_transcript() returns TranscriptMeta with correct speaker list.
- preprocess_transcript() raises TranscriptReadError for out-of-order segments.
- extract_speaker_turns() groups consecutive segments by speaker.
- TranscriptMeta has segments, speakers, and duration_ms fields.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

import pytest

from docline.readers.transcripts import (
    TranscriptMeta,
    TranscriptReadError,
    TranscriptSegment,
    extract_speaker_turns,
    preprocess_transcript,
)

# ---------------------------------------------------------------------------
# Structural: model shape (PASS in red phase)
# ---------------------------------------------------------------------------


def test_transcript_meta_default_construction() -> None:
    """TranscriptMeta can be default-constructed with empty fields."""
    meta = TranscriptMeta()
    assert meta.segments == []
    assert meta.speakers == []
    assert meta.duration_ms == 0


def test_transcript_meta_with_data() -> None:
    """TranscriptMeta holds a list of segments, a speaker list, and duration."""
    seg = TranscriptSegment(start_ms=0, end_ms=1000, speaker="Alice", text="Hello.")
    meta = TranscriptMeta(segments=[seg], speakers=["Alice"], duration_ms=1000)
    assert len(meta.segments) == 1
    assert meta.speakers == ["Alice"]
    assert meta.duration_ms == 1000


# ---------------------------------------------------------------------------
# Behavioral: preprocess_transcript (FAIL in red phase)
# ---------------------------------------------------------------------------

_SAMPLE_SEGMENTS = [
    TranscriptSegment(start_ms=0, end_ms=1000, speaker="Alice", text="Hello."),
    TranscriptSegment(start_ms=1500, end_ms=3000, speaker="Bob", text="Hi there."),
    TranscriptSegment(start_ms=3500, end_ms=5000, speaker="Alice", text="How are you?"),
]


def test_preprocess_transcript_returns_transcript_meta() -> None:
    """preprocess_transcript returns a TranscriptMeta object."""
    result = preprocess_transcript(_SAMPLE_SEGMENTS)
    assert isinstance(result, TranscriptMeta)


def test_preprocess_transcript_preserves_segment_count() -> None:
    """preprocess_transcript preserves the number of input segments."""
    result = preprocess_transcript(_SAMPLE_SEGMENTS)
    assert len(result.segments) == len(_SAMPLE_SEGMENTS)


def test_preprocess_transcript_extracts_speakers_in_order() -> None:
    """preprocess_transcript lists speakers in first-seen order."""
    result = preprocess_transcript(_SAMPLE_SEGMENTS)
    assert result.speakers == ["Alice", "Bob"]


def test_preprocess_transcript_computes_duration_ms() -> None:
    """preprocess_transcript sets duration_ms to the last segment end_ms."""
    result = preprocess_transcript(_SAMPLE_SEGMENTS)
    assert result.duration_ms == 5000


def test_preprocess_transcript_empty_list_returns_empty_meta() -> None:
    """preprocess_transcript returns empty TranscriptMeta for an empty segment list."""
    result = preprocess_transcript([])
    assert result.segments == []
    assert result.speakers == []
    assert result.duration_ms == 0


def test_preprocess_transcript_raises_for_out_of_order_segments() -> None:
    """preprocess_transcript raises TranscriptReadError for out-of-order segments."""
    out_of_order = [
        TranscriptSegment(start_ms=2000, end_ms=3000, speaker="Bob", text="Later."),
        TranscriptSegment(start_ms=0, end_ms=1000, speaker="Alice", text="Earlier."),
    ]
    with pytest.raises(TranscriptReadError):
        preprocess_transcript(out_of_order)


def test_preprocess_transcript_handles_no_speakers() -> None:
    """preprocess_transcript handles segments with no speaker attribution."""
    segments = [
        TranscriptSegment(start_ms=0, end_ms=1000, speaker=None, text="First."),
        TranscriptSegment(start_ms=1000, end_ms=2000, speaker=None, text="Second."),
    ]
    result = preprocess_transcript(segments)
    assert isinstance(result, TranscriptMeta)
    assert len(result.segments) == 2


# ---------------------------------------------------------------------------
# Behavioral: extract_speaker_turns (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_extract_speaker_turns_returns_list() -> None:
    """extract_speaker_turns returns a list of (speaker, segments) tuples."""
    meta = TranscriptMeta(segments=_SAMPLE_SEGMENTS, speakers=["Alice", "Bob"], duration_ms=5000)
    result = extract_speaker_turns(meta)
    assert isinstance(result, list)


def test_extract_speaker_turns_groups_by_speaker() -> None:
    """extract_speaker_turns groups consecutive segments by the same speaker."""
    meta = TranscriptMeta(segments=_SAMPLE_SEGMENTS, speakers=["Alice", "Bob"], duration_ms=5000)
    result = extract_speaker_turns(meta)
    speakers_in_order = [speaker for speaker, _ in result]
    assert speakers_in_order == ["Alice", "Bob", "Alice"]


def test_extract_speaker_turns_empty_meta_returns_empty_list() -> None:
    """extract_speaker_turns returns an empty list for empty TranscriptMeta."""
    meta = TranscriptMeta()
    result = extract_speaker_turns(meta)
    assert result == []
