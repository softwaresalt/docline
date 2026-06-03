"""Helpers for standardized processed-output planning across source types."""

from dataclasses import dataclass
from pathlib import Path

from docline.readers.docx import read_docx_blocks
from docline.readers.pdf import read_pdf, read_pdf_pages

_DOCX_SEGMENT_CHAR_LIMIT = 6_000


@dataclass(frozen=True)
class OutputDocumentPart:
    """A single processed markdown document planned for output emission.

    Attributes:
        body: Markdown body for the part.
        relative_output_path: Output path relative to a job root.
        title_suffix: Optional suffix appended to the derived document title.
    """

    body: str
    relative_output_path: Path
    title_suffix: str | None = None


def _chunk_text_blocks(blocks: list[str], max_chars: int) -> list[str]:
    """Chunk ordered text blocks into deterministic, size-bounded segments."""
    normalized_blocks = [block.strip() for block in blocks if block.strip()]
    if not normalized_blocks:
        return [""]

    total_chars = sum(len(block) for block in normalized_blocks)
    if len(normalized_blocks) == 1 or total_chars <= max_chars:
        return ["\n\n".join(normalized_blocks)]

    chunks: list[str] = []
    current_blocks: list[str] = []
    current_length = 0
    for block in normalized_blocks:
        projected_length = current_length + len(block) + (2 if current_blocks else 0)
        if current_blocks and projected_length > max_chars:
            chunks.append("\n\n".join(current_blocks))
            current_blocks = [block]
            current_length = len(block)
            continue
        current_blocks.append(block)
        current_length = projected_length

    if current_blocks:
        chunks.append("\n\n".join(current_blocks))
    return chunks


def _relative_output_path(relative_input_path: Path, part_index: int, part_count: int) -> Path:
    """Resolve the emitted markdown path for a processed document part."""
    if part_count == 1:
        return relative_input_path.with_suffix(".md")
    return relative_input_path.with_suffix("") / f"part-{part_index + 1:04d}.md"


def build_output_document_parts(
    file_path: Path,
    relative_input_path: Path,
) -> list[OutputDocumentPart]:
    """Plan the emitted markdown parts for a staged source file.

    Args:
        file_path: Absolute staged file path.
        relative_input_path: Relative path inside the staged ``files/`` directory.

    Returns:
        Ordered markdown output parts for the source file.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        segment_bodies = [page.strip() for page in read_pdf_pages(file_path) if page.strip()]
        if not segment_bodies:
            segment_bodies = [read_pdf(file_path)]
    elif suffix == ".docx":
        segment_bodies = _chunk_text_blocks(read_docx_blocks(file_path), _DOCX_SEGMENT_CHAR_LIMIT)
    else:
        if suffix in {".html", ".htm"}:
            from docline.fetch.html_extract import HtmlExtractionError, extract_main_content

            html = file_path.read_text(encoding="utf-8", errors="replace")
            try:
                segment_bodies = [extract_main_content(html)]
            except HtmlExtractionError:
                segment_bodies = [html]
        elif suffix in {".md", ".txt"}:
            segment_bodies = [file_path.read_text(encoding="utf-8", errors="replace")]
        else:
            segment_bodies = [file_path.read_text(encoding="utf-8", errors="replace")]

    part_count = len(segment_bodies)
    return [
        OutputDocumentPart(
            body=body,
            relative_output_path=_relative_output_path(relative_input_path, index, part_count),
            title_suffix=f"Part {index + 1}" if part_count > 1 else None,
        )
        for index, body in enumerate(segment_bodies)
    ]


__all__ = ["OutputDocumentPart", "build_output_document_parts"]
