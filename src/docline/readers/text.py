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
    raise NotImplementedError("stub: text.read_text not yet implemented")


__all__ = [
    "MAX_LINE_LENGTH",
    "TextReadError",
    "read_text",
]
