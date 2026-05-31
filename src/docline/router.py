"""Source router: classifies raw input strings into typed SourceInput objects."""

from docline.types import SourceInput, SourceKind

_TRANSCRIPT_EXTENSIONS = {".vtt", ".srt"}
_URL_PREFIXES = ("http://", "https://")


def classify_source(raw: str) -> SourceInput:
    """Classify a raw input string into a typed SourceInput.

    Classification rules (applied in order):
    1. Strings starting with ``http://`` or ``https://`` → ``SourceKind.URL``.
    2. Strings whose lowercase file extension is ``.vtt`` or ``.srt`` → ``SourceKind.TRANSCRIPT``.
    3. Everything else → ``SourceKind.FILE``.

    Args:
        raw: The raw input string (URL, file path, or transcript path).

    Returns:
        A :class:`~docline.types.SourceInput` with the resolved kind and the
        original raw string.
    """
    if raw.startswith(_URL_PREFIXES):
        return SourceInput(kind=SourceKind.URL, raw=raw)

    lower = raw.lower()
    for ext in _TRANSCRIPT_EXTENSIONS:
        if lower.endswith(ext):
            return SourceInput(kind=SourceKind.TRANSCRIPT, raw=raw)

    return SourceInput(kind=SourceKind.FILE, raw=raw)
