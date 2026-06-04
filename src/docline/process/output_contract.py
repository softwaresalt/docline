"""Helpers for standardized processed-output planning across source types."""

from dataclasses import dataclass, field
from pathlib import Path

from docline.process.segment import extract_section_title, segment_markdown
from docline.readers.docx import read_docx_blocks, read_docx_blocks_with_media
from docline.readers.pdf import read_pdf
from docline.readers.picture_sink import MediaReference, PictureSink


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
        media_files: Tuple of relative paths (under the job root) of media
            sidecar artifacts produced for this part. Empty tuple when no
            media was extracted. Surfaced as ``media_files`` in the
            per-source ``manifest.json`` entry by the application layer.
    """

    body: str
    relative_output_path: Path
    title_suffix: str | None = None
    section_title: str | None = None
    media_files: tuple[str, ...] = field(default_factory=tuple)


def _relative_output_path(
    relative_input_path: Path,
    part_index: int,
    part_count: int,
    *,
    force_multipart: bool = False,
) -> Path:
    """Resolve the emitted markdown path for a processed document part.

    When ``force_multipart`` is ``True``, the multi-part layout
    (``{source_basename}/part-NNNN.md``) is used even for single-segment
    sources so that sibling media artifacts under
    ``{source_basename}/media/...`` resolve cleanly from a sibling-relative
    markdown image reference.
    """
    if part_count == 1 and not force_multipart:
        return relative_input_path.with_suffix(".md")
    return relative_input_path.with_suffix("") / f"part-{part_index + 1:04d}.md"


def _format_media_files(references: list[MediaReference], source_dir: Path) -> tuple[str, ...]:
    """Build the relative-to-job-root paths for media references emitted by a source."""
    return tuple((source_dir / "media" / reference.filename).as_posix() for reference in references)


def build_output_document_parts(
    file_path: Path,
    relative_input_path: Path,
    *,
    layout_engine: str = "heuristic",
    picture_sink: PictureSink | None = None,
) -> list[OutputDocumentPart]:
    """Plan the emitted markdown parts for a staged source file.

    PDF and DOCX inputs are routed through heading-aware semantic
    segmentation (``segment_markdown``) so output parts respect H1/H2
    document structure rather than physical pages or arbitrary char
    bins. HTML, MD, and TXT inputs are emitted as single parts. Each
    part carries an optional ``section_title`` derived from its leading
    H1 (when present); ``section_title`` is ``None`` for char-bin
    fallback segments and non-segmenter branches.

    When ``picture_sink`` is provided AND the source is a DOCX or PDF
    that emits media artifacts, the output layout is forced to the
    multi-part form (``{source_basename}/part-NNNN.md``) so the
    markdown image references (``![](media/figure-NNNN.ext)``) resolve
    as siblings of the per-part markdown.

    Args:
        file_path: Absolute staged file path.
        relative_input_path: Relative path inside the staged ``files/`` directory.
        layout_engine: PDF layout engine selector passed through to
            :func:`docline.readers.pdf.read_pdf`. Defaults to ``"heuristic"``
            for back-compat with direct callers; production wires ``"auto"``.
        picture_sink: Optional ``PictureSink`` instance scoped to this
            source. When provided, DOCX image extraction is enabled and
            sidecar references flow into ``OutputDocumentPart.media_files``.

    Returns:
        Ordered markdown output parts for the source file.
    """
    suffix = file_path.suffix.lower()
    media_references: list[MediaReference] = []
    if suffix == ".pdf":
        rendered = read_pdf(file_path, layout_engine=layout_engine)
        segment_bodies = segment_markdown(rendered) if rendered.strip() else [""]
    elif suffix == ".docx":
        if picture_sink is not None:
            blocks, media_references = read_docx_blocks_with_media(file_path, picture_sink)
        else:
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
    has_media = bool(media_references)
    force_multipart = has_media
    source_dir = relative_input_path.with_suffix("")
    media_files = _format_media_files(media_references, source_dir) if has_media else ()

    parts: list[OutputDocumentPart] = []
    for index, body in enumerate(segment_bodies):
        # Media files are attached only to the first part of a source so the
        # manifest entries do not duplicate the references across siblings.
        part_media = media_files if has_media and index == 0 else ()
        parts.append(
            OutputDocumentPart(
                body=body,
                relative_output_path=_relative_output_path(
                    relative_input_path,
                    index,
                    part_count,
                    force_multipart=force_multipart,
                ),
                title_suffix=(f"Part {index + 1}" if part_count > 1 or force_multipart else None),
                section_title=extract_section_title(body) if body.strip() else None,
                media_files=part_media,
            )
        )
    return parts


__all__ = ["OutputDocumentPart", "build_output_document_parts"]
