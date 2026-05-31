"""Source type definitions for the docline ingestion pipeline."""

from dataclasses import dataclass
from enum import Enum


class SourceKind(Enum):
    """Classification of an input source.

    Attributes:
        FILE: A local file path (PDF, DOCX, HTML, etc.).
        TRANSCRIPT: A transcript file (.vtt or .srt).
        URL: A remote URL (http:// or https://).
    """

    FILE = "file"
    TRANSCRIPT = "transcript"
    URL = "url"


@dataclass(frozen=True)
class SourceInput:
    """A classified input source.

    Attributes:
        kind: The kind of source (FILE, TRANSCRIPT, or URL).
        raw: The original raw input string supplied by the caller.
    """

    kind: SourceKind
    raw: str
