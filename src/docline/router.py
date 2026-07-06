"""Source router: classifies raw input strings into typed SourceInput objects."""

from docline.readers.openapi.detect import is_openapi_spec
from docline.types import SourceInput, SourceKind

_TRANSCRIPT_EXTENSIONS = {".vtt", ".srt"}
_URL_PREFIXES = ("http://", "https://")


def classify_source(raw: str, *, content: str | None = None) -> SourceInput:
    """Classify a raw input string into a typed SourceInput.

    Classification rules (applied in order):

    1. Strings starting with ``http://`` or ``https://`` → ``SourceKind.URL``.
    2. Strings whose lowercase file extension is ``.vtt`` or ``.srt`` → ``SourceKind.TRANSCRIPT``.
    3. When ``content`` is supplied and content-sniffs as an OpenAPI 3.x /
       Swagger 2.0 specification → ``SourceKind.OPENAPI``.
    4. Everything else → ``SourceKind.FILE``.

    URL and transcript classification take precedence over the content sniff so
    that a remotely fetched or transcript-named source is never reclassified by
    its payload.

    Args:
        raw: The raw input string (URL, file path, or transcript path).
        content: Optional decoded file content used for OpenAPI content-sniff
            detection. When ``None`` (the default), only the string-based rules
            apply and behavior is identical to the pre-050-F router.

    Returns:
        A :class:`~docline.types.SourceInput` with the resolved kind and the
        original raw string.
    """
    lower = raw.lower()
    if lower.startswith(_URL_PREFIXES):
        return SourceInput(kind=SourceKind.URL, raw=raw)

    for ext in _TRANSCRIPT_EXTENSIONS:
        if lower.endswith(ext):
            return SourceInput(kind=SourceKind.TRANSCRIPT, raw=raw)

    if content is not None and is_openapi_spec(content):
        return SourceInput(kind=SourceKind.OPENAPI, raw=raw)

    return SourceInput(kind=SourceKind.FILE, raw=raw)
