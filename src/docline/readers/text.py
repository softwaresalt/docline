"""Plain-text reader adapter — ingest .txt and .md files as Markdown."""

from pathlib import Path

from docline.schema.models import DoclineError

# Maximum line length before a text file is flagged as potentially binary.
MAX_LINE_LENGTH: int = 4096


class TextReadError(DoclineError):
    """Raised when plain-text ingestion fails."""


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    """Read a plain-text or Markdown file and return its content.

    Args:
        path: Path to the ``.txt`` or ``.md`` file.
        encoding: Text encoding.  Defaults to ``utf-8``.

    Returns:
        The file content as a string.

    Raises:
        TextReadError: If the file cannot be decoded with the given encoding
            or if a line exceeds :data:`MAX_LINE_LENGTH` (indicating binary).
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        content = path.read_text(encoding=encoding)
    except (UnicodeDecodeError, LookupError) as err:
        raise TextReadError(f"Failed to decode {path} with encoding {encoding!r}: {err}") from err

    for line in content.splitlines():
        if len(line) > MAX_LINE_LENGTH:
            raise TextReadError(f"Line exceeds maximum length ({MAX_LINE_LENGTH}) in {path}")
    return content


__all__ = [
    "MAX_LINE_LENGTH",
    "TextReadError",
    "read_text",
]
