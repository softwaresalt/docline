"""Helpers for standardized processed-output planning across source types."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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
        source_frontmatter: Parsed YAML frontmatter from the source file
            when the source was a ``.md`` or ``.txt`` that began with a
            ``---`` fence. ``None`` when the source had no frontmatter,
            had malformed frontmatter, or was not an MD/TXT source.
            Surfaced into the docline ``source_frontmatter`` namespace by
            the application layer so downstream consumers see authorial
            metadata (``ms.author``, ``ms.topic``, etc.) preserved
            (023.001-T / 025-S).
        cross_doc_links: Tuple of ``{target_path, anchor, link_text}``
            dicts collected from intra-corpus ``[text](other.md)``
            references in the body. Empty tuple when the source had no
            cross-doc links or was not an MD/TXT source. Surfaced into
            ``docline.cross_doc_links`` as a list of dicts so downstream
            graph extraction can treat each as a first-class edge
            (024.003-T / 026-S T3).
    """

    body: str
    relative_output_path: Path
    title_suffix: str | None = None
    section_title: str | None = None
    media_files: tuple[str, ...] = field(default_factory=tuple)
    source_frontmatter: Mapping[str, Any] | None = None
    cross_doc_links: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


def _parse_md_frontmatter(text: str) -> tuple[Mapping[str, Any] | None, str]:
    """Parse and strip a leading YAML frontmatter fence from MD/TXT content.

    Recognizes the canonical Microsoft Learn / Jekyll / Hugo / MkDocs
    frontmatter form: a ``---`` fence on the very first line, followed by
    YAML key-value pairs, followed by a closing ``---`` fence.

    Args:
        text: Raw file contents.

    Returns:
        A ``(frontmatter, body)`` tuple. ``frontmatter`` is a ``Mapping``
        of the parsed YAML when present and parseable; ``None`` when the
        file had no frontmatter or the YAML was malformed. ``body`` is the
        markdown body with the frontmatter fence removed (or the original
        text when no valid frontmatter was found).
    """
    if not text:
        return None, text
    # Match leading --- fence with either LF or CRLF line endings
    if not (text.startswith("---\n") or text.startswith("---\r\n")):
        return None, text
    # Find the closing fence — must be a --- line preceded by a newline
    # Search for "\n---" (followed by newline or end of text or whitespace+newline)
    search_start = 4 if text.startswith("---\n") else 5
    end_idx = -1
    pos = search_start
    while True:
        found = text.find("\n---", pos)
        if found < 0:
            break
        # Check that "---" at found+1 is followed by line terminator or EOF
        after = found + 4
        if after >= len(text) or text[after] in ("\n", "\r"):
            end_idx = found
            break
        pos = found + 1
    if end_idx < 0:
        # No closing fence — treat as no frontmatter (malformed)
        return None, text
    yaml_text = text[search_start:end_idx]
    # Skip past the closing fence + line terminator(s)
    body_start = end_idx + 4
    if body_start < len(text) and text[body_start] == "\r":
        body_start += 1
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    body = text[body_start:]

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None, text
    if not isinstance(parsed, Mapping):
        # YAML parsed to a scalar / list / None — not usable as frontmatter
        return None, text
    return parsed, body


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
    pdf_mode: str = "auto",
    triage_output_dir: Path | None = None,
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
        pdf_mode: PDF processing pipeline mode (019-F / U4). ``"auto"``
            (default) uses the existing ``read_pdf`` path. ``"triage"``
            routes PDFs through :func:`process_pdf_triaged` for selective
            docling re-extraction; the resulting per-page outputs are
            joined and segmented through the same downstream pipeline.
            Non-PDF inputs ignore ``pdf_mode``.
        triage_output_dir: Output directory for triage splice cache.
            Required when ``pdf_mode == "triage"`` and the source is a
            PDF. Should be a per-source subdirectory of the job output
            root so splice caches don't collide across sources.

    Returns:
        Ordered markdown output parts for the source file.
    """
    suffix = file_path.suffix.lower()
    media_references: list[MediaReference] = []
    source_frontmatter: Mapping[str, Any] | None = None
    md_cross_doc_links: tuple[Mapping[str, Any], ...] = ()
    if suffix == ".pdf":
        if pdf_mode == "triage":
            if triage_output_dir is None:
                raise ValueError(
                    "build_output_document_parts: pdf_mode='triage' requires "
                    "triage_output_dir (a per-source cache directory)"
                )
            from docline.process.pdf_triage import process_pdf_triaged

            triage_result = process_pdf_triaged(file_path, output_dir=triage_output_dir)
            rendered = "\n\n".join(p for p in triage_result.pages if p.strip())
            segment_bodies = segment_markdown(rendered) if rendered.strip() else [""]
        else:
            rendered = read_pdf(file_path, layout_engine=layout_engine, picture_sink=picture_sink)
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
            # 023.001-T / 025-S: strip YAML frontmatter before passing to the
            # segmenter so the H1/H2 hierarchy validator doesn't see ``title:``
            # YAML keys as misordered headings. Parsed frontmatter flows
            # through OutputDocumentPart.source_frontmatter so the application
            # layer can preserve it under docline:source_frontmatter.
            raw_text = file_path.read_text(encoding="utf-8", errors="replace")

            # 024.002-T / 026-S T2: expand DocFx [!INCLUDE [name](path.md)]
            # directives BEFORE frontmatter strip + segmenter pass. Include
            # paths resolve relative to the host file's directory. Missing
            # includes degrade gracefully to inline comments + warnings.
            from docline.process.docfx_includes import resolve_docfx_includes

            expanded_text = resolve_docfx_includes(raw_text, base_dir=file_path.parent)

            source_frontmatter, stripped_body = _parse_md_frontmatter(expanded_text)
            # 024.001-T / 026-S T1: normalize DocFx container syntax (:::image,
            # :::moniker) into standard CommonMark so downstream consumers
            # see graphable alt-text + structural intent instead of opaque
            # ``:::container:::`` markers.
            from docline.process.docfx_normalize import normalize_docfx_containers

            normalized_body = normalize_docfx_containers(stripped_body)

            # 024.003-T / 026-S T3: collect cross-doc markdown links as
            # graph-edge metadata. Body content is unchanged; the link
            # list is attached to the OutputDocumentPart and surfaced
            # into docline:cross_doc_links by the application layer.
            from docline.process.cross_doc_links import resolve_cross_doc_links

            _, link_list = resolve_cross_doc_links(
                normalized_body, current_rel_path=relative_input_path, deduplicate=True
            )
            md_cross_doc_links = tuple(link_list)
            segment_bodies = [normalized_body]
        else:
            segment_bodies = [file_path.read_text(encoding="utf-8", errors="replace")]
            md_cross_doc_links = ()

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
        # source_frontmatter and cross_doc_links are attached only to the
        # first part for the same reason — downstream consumers see authorial
        # metadata + graph edges once per source.
        part_frontmatter = source_frontmatter if index == 0 else None
        part_cross_doc_links = md_cross_doc_links if index == 0 else ()
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
                source_frontmatter=part_frontmatter,
                cross_doc_links=part_cross_doc_links,
            )
        )
    return parts


def apply_triage_attribution(
    payload: dict[str, object],
    engine: str | None,
) -> None:
    """Merge the per-page ``engine`` attribution into ``payload['docline']``.

    Merges with existing ``docline:`` namespace keys (does not overwrite —
    see ``docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md``).

    Args:
        payload: Mutable payload dict that may already contain a ``docline``
            namespace populated by upstream validators (e.g. ``source_url``,
            ``crawl_depth``).
        engine: ``"heuristic"`` or ``"docling"``; ``None`` to leave the
            payload unchanged (non-triage runs).
    """
    if engine is None:
        return
    docline_ns = payload.setdefault("docline", {})
    if not isinstance(docline_ns, dict):
        raise ValueError(
            f"payload['docline'] must be a dict to merge engine attribution, "
            f"got {type(docline_ns).__name__}"
        )
    docline_ns["engine"] = engine


def build_triage_part_payloads(triage_result: object) -> list[dict[str, object]]:
    """Build per-page frontmatter payloads from a ``TriageResult``.

    Args:
        triage_result: :class:`docline.process.pdf_triage.TriageResult`.

    Returns:
        One payload dict per page, with the ``engine`` field merged into
        each payload's ``docline:`` namespace.
    """
    engines = getattr(triage_result, "engine_per_page", ())
    payloads: list[dict[str, object]] = []
    for engine in engines:
        payload: dict[str, object] = {}
        apply_triage_attribution(payload, engine)
        payloads.append(payload)
    return payloads


def build_triage_manifest_stats(triage_result: object) -> dict[str, int]:
    """Build the manifest-level ``triage_stats`` summary block.

    Args:
        triage_result: :class:`docline.process.pdf_triage.TriageResult`.

    Returns:
        Mapping with keys ``pages_total``, ``pages_docling``,
        ``pages_heuristic``, ``flagged_ranges``.
    """
    pages = getattr(triage_result, "pages", ())
    engines = getattr(triage_result, "engine_per_page", ())
    flagged_ranges = getattr(triage_result, "flagged_ranges", ())
    return {
        "pages_total": len(pages),
        "pages_docling": sum(1 for e in engines if e == "docling"),
        "pages_heuristic": sum(1 for e in engines if e == "heuristic"),
        "flagged_ranges": len(flagged_ranges),
    }


__all__ = [
    "OutputDocumentPart",
    "apply_triage_attribution",
    "build_output_document_parts",
    "build_triage_manifest_stats",
    "build_triage_part_payloads",
]
