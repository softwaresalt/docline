"""Helpers for standardized processed-output planning across source types."""

from dataclasses import dataclass
from pathlib import Path

from docline.process.segment import extract_section_title, segment_markdown
from docline.readers.docx import read_docx_blocks
from docline.readers.pdf import read_pdf


@dataclass(frozen=True)
class OutputDocumentPart:
    """A single processed markdown document planned for output emission.

    Attributes:
        body: Markdown body for the part.
        relative_output_path: Output path relative to a job root.
        title_suffix: Optional suffix appended to the derived document title.
        section_title: H1 heading text anchoring this part, or ``None`` when
            the part came from the char-bin fallback (no H1 boundary).
            Surfaced into the ``docline.section_title`` frontmatter field by
            the application layer.
    """

    body: str
    relative_output_path: Path
    title_suffix: str | None = None
    section_title: str | None = None


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

    PDF and DOCX inputs are routed through heading-aware semantic
    segmentation (``segment_markdown``) so output parts respect H1/H2
    document structure rather than physical pages or arbitrary char
    bins. HTML, MD, and TXT inputs are emitted as single parts. Each
    part carries an optional ``section_title`` derived from its leading
    H1 (when present); ``section_title`` is ``None`` for char-bin
    fallback segments and non-segmenter branches.

    Args:
        file_path: Absolute staged file path.
        relative_input_path: Relative path inside the staged ``files/`` directory.

    Returns:
        Ordered markdown output parts for the source file.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        rendered = read_pdf(file_path)
        segment_bodies = segment_markdown(rendered) if rendered.strip() else [""]
    elif suffix == ".docx":
        blocks = read_docx_blocks(file_path)
        joined = "\n\n".join(block.strip() for block in blocks if block.strip())
        segment_bodies = segment_markdown(joined) if joined else [""]
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
            section_title=extract_section_title(body) if body.strip() else None,
        )
        for index, body in enumerate(segment_bodies)
    ]


__all__ = ["OutputDocumentPart", "build_output_document_parts"]
