"""PDF reader — extract text content from PDF files without external dependencies.

Uses the Python standard library ``zlib`` module to decompress ``FlateDecode``
content streams and a regex-based PDF operator parser to extract text from
``BT``/``ET`` text blocks.  Supports:

* Uncompressed content streams
* ``FlateDecode`` (zlib-compressed) content streams
* Literal string operators: ``(text) Tj``
* Array text operators: ``[(text)] TJ``
* Hex string operators: ``<hexdigits> Tj``

Returns an empty string for PDFs with no extractable text rather than raising.
"""

import re
import zlib
from pathlib import Path

from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Compiled patterns — reused across calls for performance
# ---------------------------------------------------------------------------

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_FLATEDECODE_RE = re.compile(rb"/FlateDecode\b")
_BT_ET_RE = re.compile(rb"BT\s+(.*?)\s*ET", re.DOTALL)
_TJ_LITERAL_RE = re.compile(rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*Tj", re.DOTALL)
_TJ_ARRAY_RE = re.compile(rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)", re.DOTALL)
_TJ_HEX_RE = re.compile(rb"<([0-9A-Fa-f]+)>\s*Tj")
_TJ_ARRAY_OP_RE = re.compile(rb"\[([^\]]*)\]\s*TJ", re.DOTALL)
_FILTER_RE = re.compile(rb"<<[^>]*?/Filter\s*(/\w+)[^>]*?>>", re.DOTALL)
_ESCAPE_RE = re.compile(rb"\\(.)", re.DOTALL)

_PDF_ESCAPE_MAP: dict[bytes, bytes] = {
    b"n": b"\n",
    b"r": b"\r",
    b"t": b"\t",
    b"b": b"\b",
    b"f": b"\f",
    b"(": b"(",
    b")": b")",
    b"\\": b"\\",
}


class PdfReadError(DoclineError):
    """Raised when PDF extraction fails."""


def _is_utf16_bytes(data: bytes) -> tuple[bool, str]:
    """Detect whether ``data`` looks like UTF-16 and return encoding name.

    Checks (in order):

    1. UTF-16BE BOM (``\\xfe\\xff``)
    2. UTF-16LE BOM (``\\xff\\xfe``)
    3. Heuristic: if the byte sequence has even length and more than half of
       the even-indexed bytes are NUL, treat as UTF-16BE without BOM.
    4. Heuristic: if more than half of the odd-indexed bytes are NUL, treat
       as UTF-16LE without BOM.

    Args:
        data: Raw bytes to inspect.

    Returns:
        A ``(detected, encoding)`` tuple.  ``detected`` is ``True`` when a
        UTF-16 encoding was identified; ``encoding`` is the codec name or
        ``""`` when not detected.
    """
    if data.startswith(b"\xfe\xff"):
        return True, "utf-16-be"
    if data.startswith(b"\xff\xfe"):
        return True, "utf-16-le"
    if len(data) >= 4 and len(data) % 2 == 0:
        null_even = sum(1 for i in range(0, len(data), 2) if data[i] == 0)
        if null_even > len(data) // 4:
            return True, "utf-16-be"
        null_odd = sum(1 for i in range(1, len(data), 2) if data[i] == 0)
        if null_odd > len(data) // 4:
            return True, "utf-16-le"
    return False, ""


def _unescape_pdf_literal(raw: bytes) -> str:
    """Decode PDF literal string escape sequences.

    After unescaping, the raw bytes are inspected for UTF-16 encoding (via
    BOM or NUL-interleave heuristic) before falling back to latin-1.

    Args:
        raw: Raw bytes from inside a ``(...)`` PDF string.

    Returns:
        Decoded Python string.
    """

    def _replace(m: re.Match[bytes]) -> bytes:
        ch = m.group(1)
        return _PDF_ESCAPE_MAP.get(ch, ch)

    unescaped = _ESCAPE_RE.sub(_replace, raw)
    detected, encoding = _is_utf16_bytes(unescaped)
    if detected:
        text = unescaped.decode(encoding, errors="replace")
        # Strip BOM character if present
        return text.lstrip("\ufeff")
    return unescaped.decode("latin-1", errors="replace")


def _decode_hex_string(hex_bytes: bytes) -> str:
    """Decode a PDF hex string (e.g. ``48454C4C4F``) to text.

    After hex-decoding, the raw bytes are inspected for UTF-16 encoding (via
    BOM or NUL-interleave heuristic) before falling back to latin-1.

    Args:
        hex_bytes: ASCII hex digits (no angle brackets).

    Returns:
        Decoded Python string.
    """
    try:
        raw = bytes.fromhex(hex_bytes.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return ""
    detected, encoding = _is_utf16_bytes(raw)
    if detected:
        text = raw.decode(encoding, errors="replace")
        return text.lstrip("\ufeff")
    return raw.decode("latin-1", errors="replace")


def _decompress_stream(data: bytes) -> bytes:
    """Attempt to decompress a FlateDecode stream.

    Tries standard zlib first, then raw deflate (without zlib header).

    Args:
        data: Compressed stream bytes.

    Returns:
        Decompressed bytes, or the original data if decompression fails.
    """
    try:
        return zlib.decompress(data)
    except zlib.error:
        pass
    try:
        return zlib.decompress(data, -zlib.MAX_WBITS)
    except zlib.error:
        return data  # Return as-is; extraction may still find plain-text operators


def _extract_text_from_stream(stream_data: bytes) -> list[str]:
    """Extract text strings from a single PDF content stream.

    Processes BT/ET text blocks and extracts all ``Tj``, ``TJ``, and hex
    string operators.

    Args:
        stream_data: Raw (possibly decompressed) content stream bytes.

    Returns:
        List of extracted text strings.
    """
    texts: list[str] = []
    for bt_match in _BT_ET_RE.finditer(stream_data):
        block = bt_match.group(1)

        # (text) Tj — literal string
        for m in _TJ_LITERAL_RE.finditer(block):
            text = _unescape_pdf_literal(m.group(1))
            if text:
                texts.append(text)

        # [(text1) 10 (text2)] TJ — array of text
        for array_match in _TJ_ARRAY_OP_RE.finditer(block):
            array_content = array_match.group(1)
            for m in _TJ_ARRAY_RE.finditer(array_content):
                text = _unescape_pdf_literal(m.group(1))
                if text:
                    texts.append(text)

        # <hexdigits> Tj — hex string
        for m in _TJ_HEX_RE.finditer(block):
            text = _decode_hex_string(m.group(1))
            if text:
                texts.append(text)

    return texts


def _extract_pdf_text(data: bytes) -> str:
    """Extract all text from PDF raw bytes.

    Iterates over all content streams in the PDF byte blob, decompresses
    FlateDecode streams, then extracts text operators from each stream.

    Args:
        data: Full PDF file bytes.

    Returns:
        Concatenated extracted text, or ``""`` if no text was found.
    """
    texts: list[str] = []
    for stream_match in _STREAM_RE.finditer(data):
        stream_data = stream_match.group(1)
        # Check if the preceding bytes indicate a FlateDecode filter.
        # We look 512 bytes before the stream keyword for the dict.
        pre_start = max(0, stream_match.start() - 512)
        pre_bytes = data[pre_start : stream_match.start()]
        if _FLATEDECODE_RE.search(pre_bytes):
            stream_data = _decompress_stream(stream_data)
        texts.extend(_extract_text_from_stream(stream_data))
    return " ".join(texts)


def read_pdf(path: Path) -> str:
    """Extract text content from a PDF file and return it as Markdown.

    Extracts text from uncompressed and FlateDecode content streams using
    PDF operator parsing.  Returns an empty string for PDFs with no
    extractable text.

    Args:
        path: Path to the PDF file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.

    Returns:
        Markdown text extracted from the PDF (may be empty for scan-only PDFs).

    Raises:
        PdfReadError: If PDF parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise PdfReadError(f"Not a valid PDF file: {path}")
    return _extract_pdf_text(raw)


__all__ = [
    "PdfReadError",
    "read_pdf",
]
