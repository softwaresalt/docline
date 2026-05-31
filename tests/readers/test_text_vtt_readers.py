"""Test harness for 003.009-T — Add text and VTT adapters.

Acceptance criteria:
- read_text() returns the file content as a string.
- read_vtt() returns an ordered list of TranscriptSegment objects.
- TranscriptSegment has start_ms, end_ms, speaker, text fields.
- TextReadError and TranscriptReadError are DoclineError subclasses.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

from pathlib import Path

import pytest

from docline.readers.text import TextReadError, read_text
from docline.readers.transcripts import TranscriptReadError, TranscriptSegment, read_vtt
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy and model shape (PASS in red phase)
# ---------------------------------------------------------------------------


def test_text_read_error_is_docline_error() -> None:
    """TextReadError is a subclass of DoclineError."""
    err = TextReadError("read failed")
    assert isinstance(err, DoclineError)


def test_transcript_read_error_is_docline_error() -> None:
    """TranscriptReadError is a subclass of DoclineError."""
    err = TranscriptReadError("vtt parse failed")
    assert isinstance(err, DoclineError)


def test_transcript_segment_construction() -> None:
    """TranscriptSegment can be constructed with all required fields."""
    seg = TranscriptSegment(start_ms=0, end_ms=1000, speaker="Alice", text="Hello world.")
    assert seg.start_ms == 0
    assert seg.end_ms == 1000
    assert seg.speaker == "Alice"
    assert seg.text == "Hello world."


def test_transcript_segment_no_speaker() -> None:
    """TranscriptSegment accepts None for the speaker field."""
    seg = TranscriptSegment(start_ms=500, end_ms=2000, speaker=None, text="Unattributed.")
    assert seg.speaker is None


def test_transcript_segment_is_frozen() -> None:
    """TranscriptSegment is immutable (frozen dataclass)."""
    seg = TranscriptSegment(start_ms=0, end_ms=500, speaker="Bob", text="Hi.")
    with pytest.raises((AttributeError, TypeError)):
        seg.text = "Modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Behavioral: read_text (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_read_text_returns_string(tmp_path: Path) -> None:
    """read_text returns the file content as a string."""
    txt = tmp_path / "sample.txt"
    txt.write_text("Hello, world.", encoding="utf-8")
    result = read_text(txt)
    assert isinstance(result, str)


def test_read_text_returns_correct_content(tmp_path: Path) -> None:
    """read_text returns the exact file content."""
    content = "Line one.\nLine two.\n"
    txt = tmp_path / "doc.txt"
    txt.write_text(content, encoding="utf-8")
    result = read_text(txt)
    assert result == content


def test_read_text_works_with_markdown_file(tmp_path: Path) -> None:
    """read_text returns content for a .md file."""
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nBody text.", encoding="utf-8")
    result = read_text(md)
    assert "# Title" in result


def test_read_text_raises_for_nonexistent_file(tmp_path: Path) -> None:
    """read_text raises FileNotFoundError for a non-existent file."""
    txt = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        read_text(txt)


def test_read_text_accepts_encoding_parameter(tmp_path: Path) -> None:
    """read_text accepts an encoding parameter."""
    txt = tmp_path / "latin.txt"
    txt.write_bytes("caf\xe9".encode("latin-1"))
    result = read_text(txt, encoding="latin-1")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Behavioral: read_vtt (FAIL in red phase)
# ---------------------------------------------------------------------------

_MINIMAL_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:02.500
Hello world.

00:00:03.000 --> 00:00:05.000
Second line.
"""

_VTT_WITH_SPEAKERS = (
    "WEBVTT\n\n"
    "00:00:00.000 --> 00:00:02.000\n"
    "<v Alice>Hello.</v>\n\n"
    "00:00:02.500 --> 00:00:04.000\n"
    "<v Bob>Hi there.</v>\n"
)


def test_read_vtt_returns_list(tmp_path: Path) -> None:
    """read_vtt returns a list."""
    vtt = tmp_path / "sample.vtt"
    vtt.write_text(_MINIMAL_VTT, encoding="utf-8")
    result = read_vtt(vtt)
    assert isinstance(result, list)


def test_read_vtt_returns_transcript_segments(tmp_path: Path) -> None:
    """read_vtt returns a list of TranscriptSegment objects."""
    vtt = tmp_path / "sample.vtt"
    vtt.write_text(_MINIMAL_VTT, encoding="utf-8")
    result = read_vtt(vtt)
    assert all(isinstance(s, TranscriptSegment) for s in result)


def test_read_vtt_parses_two_cues(tmp_path: Path) -> None:
    """read_vtt returns two segments for two VTT cues."""
    vtt = tmp_path / "sample.vtt"
    vtt.write_text(_MINIMAL_VTT, encoding="utf-8")
    result = read_vtt(vtt)
    assert len(result) == 2


def test_read_vtt_first_segment_starts_at_zero(tmp_path: Path) -> None:
    """read_vtt first segment has start_ms=0 for 00:00:00.000."""
    vtt = tmp_path / "sample.vtt"
    vtt.write_text(_MINIMAL_VTT, encoding="utf-8")
    result = read_vtt(vtt)
    assert result[0].start_ms == 0


def test_read_vtt_parses_speaker_cues(tmp_path: Path) -> None:
    """read_vtt extracts speaker identifiers from <v Speaker> cues."""
    vtt = tmp_path / "speakers.vtt"
    vtt.write_text(_VTT_WITH_SPEAKERS, encoding="utf-8")
    result = read_vtt(vtt)
    speakers = {s.speaker for s in result if s.speaker}
    assert "Alice" in speakers
    assert "Bob" in speakers


def test_read_vtt_raises_for_nonexistent_file(tmp_path: Path) -> None:
    """read_vtt raises FileNotFoundError for a non-existent file."""
    vtt = tmp_path / "missing.vtt"
    with pytest.raises(FileNotFoundError):
        read_vtt(vtt)


def test_read_vtt_raises_for_invalid_vtt(tmp_path: Path) -> None:
    """read_vtt raises TranscriptReadError for a non-VTT file."""
    vtt = tmp_path / "bad.vtt"
    vtt.write_text("this is not a vtt file at all\nno header\n", encoding="utf-8")
    with pytest.raises(TranscriptReadError):
        read_vtt(vtt)
