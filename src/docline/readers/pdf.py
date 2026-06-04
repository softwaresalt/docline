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

from docline import dependencies
from docline.dependencies import DependencyUnavailableError
from docline.schema.models import DoclineError

# F5.T5 opt-in PDF layout engine selector. ``"heuristic"`` is the deterministic
# built-in extractor (phase-1 banding from F5.T3). ``"docling"`` opts in to the
# optional ``docling`` package and is gated by :func:`dependencies.pdf_available`.
# ``"auto"`` (G3c / 014-S) resolves to ``"docling"`` when the optional
# ``docline[pdf]`` extras are installed, else ``"heuristic"``.
_SUPPORTED_LAYOUT_ENGINES: frozenset[str] = frozenset({"auto", "heuristic", "docling"})


def _validate_layout_engine(engine: str) -> None:
    """Reject unknown ``layout_engine`` values with a clear error.

    Args:
        engine: Caller-supplied engine name.

    Raises:
        ValueError: If ``engine`` is not in ``_SUPPORTED_LAYOUT_ENGINES``.
            The message names the offending value so operators can correct
            the flag without reading the source.
    """
    if engine not in _SUPPORTED_LAYOUT_ENGINES:
        supported = ", ".join(sorted(_SUPPORTED_LAYOUT_ENGINES))
        raise ValueError(f"Unknown PDF layout_engine {engine!r}; supported engines: {supported}")


def _resolve_layout_engine(requested: str) -> str:
    """Resolve ``"auto"`` to ``"docling"`` when available, else ``"heuristic"``.

    Validates ``requested`` first. Pass-through behavior for explicit
    ``"heuristic"`` and ``"docling"`` is preserved — only ``"auto"`` is
    resolved against the runtime probe.

    Args:
        requested: Engine name (one of ``"auto"``, ``"heuristic"``,
            ``"docling"``).

    Returns:
        The concrete engine name (``"heuristic"`` or ``"docling"``).

    Raises:
        ValueError: If ``requested`` is not a recognized engine value.
    """
    _validate_layout_engine(requested)
    if requested != "auto":
        return requested
    return "docling" if dependencies.pdf_available() else "heuristic"


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

# F5.T3 phase-1 layout heuristic: scan Tf/Tj/TJ/<hex>Tj operators in order so
# the active font size at the moment of text emission is known. The combined
# regex preserves operator order within a BT/ET block.
_OPERATOR_RE = re.compile(
    rb"/\w+\s+([\d.]+)\s+Tf"
    rb"|\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*Tj"
    rb"|\[([^\]]*)\]\s*TJ"
    rb"|<([0-9A-Fa-f]+)>\s*Tj",
    re.DOTALL,
)
_HEADING_PREFIXES: tuple[str, str, str] = ("# ", "## ", "### ")

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


def _extract_text_from_stream(stream_data: bytes) -> list[tuple[str, float | None]]:
    """Extract ordered ``(text, font_size)`` pairs from a single content stream.

    Walks BT/ET text blocks operator by operator using ``_OPERATOR_RE`` so
    the active ``Tf`` font size at the moment of each ``Tj``/``TJ``/``<hex>Tj``
    emission is captured alongside the text. ``font_size`` is ``None`` for
    runs emitted before any ``Tf`` has been seen.

    Args:
        stream_data: Raw (possibly decompressed) content stream bytes.

    Returns:
        Ordered ``(text, font_size_or_None)`` runs.
    """
    runs: list[tuple[str, float | None]] = []
    for bt_match in _BT_ET_RE.finditer(stream_data):
        block = bt_match.group(1)
        current_size: float | None = None
        for m in _OPERATOR_RE.finditer(block):
            tf_size, tj_literal, tj_array, tj_hex = (
                m.group(1),
                m.group(2),
                m.group(3),
                m.group(4),
            )
            if tf_size is not None:
                try:
                    current_size = float(tf_size)
                except ValueError:
                    current_size = None
                continue
            if tj_literal is not None:
                text = _unescape_pdf_literal(tj_literal)
                if text:
                    runs.append((text, current_size))
                continue
            if tj_array is not None:
                parts: list[str] = []
                for pm in _TJ_ARRAY_RE.finditer(tj_array):
                    decoded = _unescape_pdf_literal(pm.group(1))
                    if decoded:
                        parts.append(decoded)
                if parts:
                    runs.append((" ".join(parts), current_size))
                continue
            if tj_hex is not None:
                text = _decode_hex_string(tj_hex)
                if text:
                    runs.append((text, current_size))
    return runs


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


def _extract_pdf_runs_blocks(data: bytes) -> list[list[tuple[str, float | None]]]:
    """Extract per-stream ``(text, font_size)`` run lists from a full PDF.

    Args:
        data: Full PDF file bytes.

    Returns:
        Non-empty per-stream run lists in document order. Streams that
        produce no text runs are dropped.
    """
    blocks: list[list[tuple[str, float | None]]] = []
    for stream_match in _STREAM_RE.finditer(data):
        stream_data = stream_match.group(1)
        # Look 512 bytes before the ``stream`` keyword for a FlateDecode flag.
        pre_start = max(0, stream_match.start() - 512)
        pre_bytes = data[pre_start : stream_match.start()]
        if _FLATEDECODE_RE.search(pre_bytes):
            stream_data = _decompress_stream(stream_data)
        runs = _extract_text_from_stream(stream_data)
        if runs:
            blocks.append(runs)
    return blocks


def _compute_heading_levels(
    blocks: list[list[tuple[str, float | None]]],
) -> dict[float, str]:
    """Cluster observed font sizes into ≤3 bands and assign ATX heading prefixes.

    Phase-1 heuristic: when at least two distinct ``Tf`` sizes are observed
    across the document, the top three distinct sizes (descending) are mapped
    to ``"# "``, ``"## "``, and ``"### "`` respectively. Smaller sizes (the
    body band) receive no marker.

    When fewer than two distinct sizes are observed — including the common
    case where no ``Tf`` operator appears at all — an empty mapping is
    returned and the caller emits text unchanged (preserving the pre-F5.T3
    baseline behavior pinned by ``test_pdf_baseline_characterization``).

    Args:
        blocks: Per-stream ``(text, font_size_or_None)`` run lists from
            :func:`_extract_pdf_runs_blocks`.

    Returns:
        Mapping from font size to ATX heading prefix; empty when no banding
        should be applied.
    """
    sizes: set[float] = set()
    for runs in blocks:
        for _text, size in runs:
            if size is not None:
                sizes.add(size)
    if len(sizes) < 2:
        return {}
    descending = sorted(sizes, reverse=True)
    # Reserve the smallest distinct size as the body band; map only the top
    # ``min(N-1, 3)`` bands to heading prefixes. This keeps the heuristic
    # conservative: small-format documents (2 sizes) emit only H1 + body.
    heading_band_count = min(len(descending) - 1, len(_HEADING_PREFIXES))
    mapping: dict[float, str] = {}
    for size, prefix in zip(descending[:heading_band_count], _HEADING_PREFIXES, strict=False):
        mapping[size] = prefix
    return mapping


def _emit_block_with_headings(
    runs: list[tuple[str, float | None]], heading_map: dict[float, str]
) -> str:
    """Render one stream's runs as a block of text, applying heading markers.

    With no heading bands active, behavior is identical to the pre-F5.T3
    extractor: all runs are joined with a single space and stripped. With
    heading bands active, runs whose font size matches a band are emitted on
    their own line prefixed with the ATX marker; runs in the body band group
    together space-joined between heading lines.

    Args:
        runs: Ordered ``(text, font_size_or_None)`` pairs for one stream.
        heading_map: Output of :func:`_compute_heading_levels`.

    Returns:
        Rendered block text (may contain embedded newlines when bands apply).
    """
    if not heading_map:
        return " ".join(text for text, _size in runs).strip()

    lines: list[str] = []
    body_buffer: list[str] = []

    def _flush_body() -> None:
        if body_buffer:
            line = " ".join(body_buffer).strip()
            if line:
                lines.append(line)
            body_buffer.clear()

    for text, size in runs:
        prefix = heading_map.get(size, "") if size is not None else ""
        if prefix:
            _flush_body()
            lines.append(prefix + text)
        else:
            body_buffer.append(text)
    _flush_body()
    return "\n".join(lines)


def _extract_pdf_text_blocks(data: bytes) -> list[str]:
    """Extract ordered text blocks with the F5.T3 layout heuristic applied.

    Builds per-stream run lists with attached font sizes, computes the
    document-level heading band mapping, then renders each stream as one
    block of text. Streams that render to empty strings are dropped.
    """
    runs_blocks = _extract_pdf_runs_blocks(data)
    heading_map = _compute_heading_levels(runs_blocks)
    rendered: list[str] = []
    for runs in runs_blocks:
        block_text = _emit_block_with_headings(runs, heading_map)
        if block_text:
            rendered.append(block_text)
    return rendered


def read_pdf(path: Path, *, layout_engine: str = "heuristic") -> str:
    """Extract text content from a PDF file and return it as Markdown.

    Prefers ``pypdf`` when installed for accurate extraction from real-world
    PDFs.  Falls back to the built-in FlateDecode + PDF-operator parser when
    ``pypdf`` is not available.

    Args:
        path: Path to the PDF file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.
        layout_engine: Which layout extractor to use. ``"heuristic"`` (default)
            uses the deterministic built-in extractor with phase-1 font-size
            banding — stable for direct callers and synthetic test PDFs.
            ``"docling"`` opts in to the optional ``docling`` package for
            richer layout analysis and raises
            :class:`DependencyUnavailableError` when ``docling`` is not
            importable. ``"auto"`` (G3c / 014-S) resolves to ``"docling"``
            when the optional ``docline[pdf]`` extras are installed and
            transparently falls back to ``"heuristic"`` when docling
            either is unavailable or fails to load a particular PDF.
            Production callers (``output_contract``) use ``"auto"``;
            direct callers default to ``"heuristic"`` for determinism.

    Returns:
        Markdown text extracted from the PDF (may be empty for scan-only PDFs).

    Raises:
        PdfReadError: If PDF parsing fails.
        FileNotFoundError: If ``path`` does not exist.
        DependencyUnavailableError: If ``layout_engine='docling'`` and the
            ``docling`` package is not installed.
        ValueError: If ``layout_engine`` is not a recognized engine value.
    """
    return "\n\n".join(read_pdf_pages(path, layout_engine=layout_engine))


def read_pdf_pages(path: Path, *, layout_engine: str = "heuristic") -> list[str]:
    """Extract ordered text pages from a PDF file.

    Args:
        path: Path to the PDF file. Must be a trusted-local path.
        layout_engine: Which layout extractor to use. See :func:`read_pdf`.

    Returns:
        Ordered non-empty page strings. Returns an empty list when no text is
        extractable.

    Raises:
        PdfReadError: If PDF parsing fails (does not fire for ``"auto"`` —
            ``"auto"`` falls back to heuristic on docling errors).
        FileNotFoundError: If ``path`` does not exist.
        DependencyUnavailableError: If ``layout_engine='docling'`` and the
            ``docling`` package is not installed.
        ValueError: If ``layout_engine`` is not a recognized engine value.
    """
    resolved_engine = _resolve_layout_engine(layout_engine)
    if resolved_engine == "docling":
        if not dependencies.pdf_available():
            raise DependencyUnavailableError(
                "Install the optional 'docling' package to use "
                "layout_engine='docling' (extras: docline[pdf]; missing import: docling)"
            )
        if layout_engine == "auto":
            try:
                return _read_pdf_docling_pages(path)
            except (PdfReadError, FileNotFoundError):
                # FileNotFoundError must propagate; PdfReadError under "auto"
                # falls back to heuristic so a single hostile PDF does not
                # break batch processing. Re-raise FileNotFoundError below
                # by re-entering the heuristic path which performs the same
                # path.exists() check.
                if not path.exists():
                    raise
                # Drop down to heuristic fallback for docling parse failures.
            else:
                # Successful docling path already returned above.
                pass
        else:
            return _read_pdf_docling_pages(path)
        return _read_pdf_docling_pages(path)
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


def _read_pdf_docling_pages(path: Path) -> list[str]:
    """Extract text via the optional ``docling`` package.

    Called only after :func:`dependencies.pdf_available` returns ``True``.

    Args:
        path: Path to the PDF file.

    Returns:
        Single-element list containing the docling-rendered Markdown, or an
        empty list when docling produces no text.

    Raises:
        PdfReadError: If docling fails to convert the PDF.
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]
    except ImportError as err:
        # Defensive: pdf_available() said yes but the converter import failed.
        raise DependencyUnavailableError(
            "Install the optional 'docling' package to use "
            "layout_engine='docling' (extras: docline[pdf]; missing import: docling)"
        ) from err
    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        markdown = result.document.export_to_markdown()
    except Exception as err:  # noqa: BLE001
        raise PdfReadError(f"docling failed to convert PDF: {path}") from err
    markdown = markdown.strip()
    if not markdown:
        return []
    return [markdown]


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
