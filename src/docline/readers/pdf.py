"""PDF reader — extract text content from PDF files.

Primary extractor: ``pypdf`` when installed.  Provides accurate text
extraction from real-world PDFs including those produced by Microsoft Office,
Azure documentation, and Power BI tooling.

Fallback extractor: built-in ``zlib``-based stream parser.  Handles simple
uncompressed and FlateDecode PDFs when ``pypdf`` is not available.  May
produce garbled output for PDFs with complex encoding or font subsetting.

Supported by the built-in fallback only:

* Uncompressed content streams
* ``FlateDecode`` (zlib-compressed) content streams
* Literal string operators: ``(text) Tj``
* Array text operators: ``[(text)] TJ``
* Hex string operators: ``<hexdigits> Tj``

Returns an empty string for PDFs with no extractable text rather than raising.
"""

import io
import re
import zlib
from pathlib import Path

from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Optional pypdf integration — preferred when installed
# ---------------------------------------------------------------------------

try:
    import pypdf as _pypdf  # type: ignore[import-untyped]

    _PYPDF_AVAILABLE: bool = True
except ImportError:
    _pypdf = None  # type: ignore[assignment]
    _PYPDF_AVAILABLE = False

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
    return "\n\n".join(_extract_pdf_text_blocks(data))


def _extract_pdf_text_blocks(data: bytes) -> list[str]:
    """Extract ordered text blocks from PDF content streams."""
    texts: list[str] = []
    for stream_match in _STREAM_RE.finditer(data):
        stream_data = stream_match.group(1)
        # Check if the preceding bytes indicate a FlateDecode filter.
        # We look 512 bytes before the stream keyword for the dict.
        pre_start = max(0, stream_match.start() - 512)
        pre_bytes = data[pre_start : stream_match.start()]
        if _FLATEDECODE_RE.search(pre_bytes):
            stream_data = _decompress_stream(stream_data)
        block_text = " ".join(_extract_text_from_stream(stream_data)).strip()
        if block_text:
            texts.append(block_text)
    return texts


def read_pdf(path: Path) -> str:
    """Extract text content from a PDF file and return it as Markdown.

    Prefers ``pypdf`` when installed for accurate extraction from real-world
    PDFs.  Falls back to the built-in FlateDecode + PDF-operator parser when
    ``pypdf`` is not available.

    Args:
        path: Path to the PDF file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.

    Returns:
        Markdown text extracted from the PDF (may be empty for scan-only PDFs).

    Raises:
        PdfReadError: If PDF parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    return "\n\n".join(read_pdf_pages(path))


def read_pdf_pages(path: Path) -> list[str]:
    """Extract ordered text pages from a PDF file.

    Args:
        path: Path to the PDF file. Must be a trusted-local path.

    Returns:
        Ordered non-empty page strings. Returns an empty list when no text is
        extractable.

    Raises:
        PdfReadError: If PDF parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise PdfReadError(f"Not a valid PDF file: {path}")
    if _PYPDF_AVAILABLE:
        pages = _read_pdf_pypdf_pages(raw)
        if pages:
            return pages
    return _extract_pdf_text_blocks(raw)


def _read_pdf_pypdf_pages(raw: bytes) -> list[str]:
    """Extract ordered page text with ``pypdf`` when available."""
    try:
        # _pypdf is guaranteed non-None here: this helper is only called when
        # _PYPDF_AVAILABLE is True, which is set only after a successful import.
        reader = _pypdf.PdfReader(io.BytesIO(raw))  # type: ignore[union-attr]
        return [
            page_text
            for page_text in (
                reader.pages[i].extract_text() or "" for i in range(len(reader.pages))
            )
            if page_text
        ]
    except Exception:  # noqa: BLE001
        # pypdf could not parse this PDF (truncated, non-conforming, or unusual
        # encoding). Fall back to the built-in extractor so synthetic/minimal
        # PDFs still produce output rather than failing hard.
        return []


__all__ = [
    "PdfReadError",
    "read_pdf",
    "read_pdf_pages",
]
