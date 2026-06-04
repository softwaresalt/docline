"""Failing-first tests for G3b frontmatter referentiality + chunk anchor default.

Covers ten referentiality scenarios validating the `docline:` namespace
fields (`parent_document_id`, `part_index`, `total_parts`, `prev_part`,
`next_part`, `section_title`) and one scenario validating the production
call-site default flip for chunk anchors. Written before the implementation
lands in task 014.002-T / 014.003-T (TDD RED phase).
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source

# ---------------------------------------------------------------------------
# Helpers (mirror tests/elt/test_process_regression.py)
# ---------------------------------------------------------------------------


def _write_staging_job(
    staging_root: Path,
    source_key: str,
    files: dict[str, bytes],
) -> StagingJob:
    """Write a staging job with the supplied files on disk."""
    job_id = make_job_id(source_key)
    staging_name = staging_root.name
    cache_rel = build_cache_path(staging_name, job_id)
    cache_abs = staging_root.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        dest = files_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    metadata = SourceMetadata(source=sanitize_source(source_key), fetch_timestamp=datetime.now(UTC))
    job = StagingJob(job_id=job_id, metadata=metadata, cache_path=cache_rel, complete=True)
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job


def _make_minimal_docx() -> bytes:
    """Return minimal valid DOCX bytes with a single 'Hello' paragraph."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns}">'
        "<w:body><w:p><w:r><w:t>Hello DOCX content</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    types = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _make_pdf_bytes_multi_page(texts: list[str]) -> bytes:
    """Construct a minimal multi-page PDF with one text stream per page."""
    if not texts:
        raise ValueError("texts must contain at least one page")
    objects: list[bytes] = [b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"]
    page_refs: list[str] = []
    next_object_id = 3
    for text in texts:
        page_object_id = next_object_id
        content_object_id = next_object_id + 1
        next_object_id += 2
        page_refs.append(f"{page_object_id} 0 R")
        content_stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
        objects.append(
            (
                f"{page_object_id} 0 obj\n"
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
                f" /Contents {content_object_id} 0 R >>\nendobj\n"
            ).encode("ascii")
        )
        objects.append(
            b""
            + f"{content_object_id} 0 obj\n<< /Length {len(content_stream)} >>\n".encode("ascii")
            + b"stream\n"
            + content_stream
            + b"\nendstream\nendobj\n"
        )
    pages_object = (
        f"2 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(texts)} >>\nendobj\n"
    ).encode("ascii")
    return b"%PDF-1.4\n" + objects[0] + pages_object + b"".join(objects[1:]) + b"%%EOF\n"


def _process_and_load_parts(
    tmp_path: Path, source_key: str, files: dict[str, bytes]
) -> list[dict[str, Any]]:
    """Run execute_process and return ordered list of {path, body, frontmatter} per emitted part."""
    staging_dir = tmp_path / "staging"
    job = _write_staging_job(staging_dir, source_key, files)
    output_dir = tmp_path / "output"
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str(output_dir.relative_to(tmp_path)),
    )
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)
    finally:
        os.chdir(original_cwd)
    assert result.success is True, f"process failed: {result.error}"

    job_root = output_dir / job.job_id
    manifest = json.loads((job_root / "manifest.json").read_text(encoding="utf-8"))
    parts: list[dict[str, Any]] = []
    for entry in manifest["documents"]:
        out_path = job_root / entry["output_path"]
        content = out_path.read_text(encoding="utf-8")
        assert content.startswith("---\n"), f"missing frontmatter in {out_path}"
        _, fm_block, body = content.split("---", 2)
        fm = yaml.safe_load(fm_block)
        parts.append({"path": out_path, "body": body, "frontmatter": fm, "manifest_entry": entry})
    return parts


# ---------------------------------------------------------------------------
# Referentiality scenarios
# ---------------------------------------------------------------------------


def test_single_part_output_has_unit_referentiality(tmp_path: Path) -> None:
    """Single-part DOCX has unit referentiality fields populated.

    Asserts part_index=1, total_parts=1, prev/next=None, parent_document_id present.
    """
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/hello.docx",
        {"hello.docx": _make_minimal_docx()},
    )
    assert len(parts) == 1
    docline = parts[0]["frontmatter"]["docline"]
    assert docline["part_index"] == 1
    assert docline["total_parts"] == 1
    assert docline["prev_part"] is None
    assert docline["next_part"] is None
    assert isinstance(docline["parent_document_id"], str)
    assert len(docline["parent_document_id"]) == 16


def test_multi_part_output_part_index_and_total_parts(tmp_path: Path) -> None:
    """Three-H1 PDF yields three parts with sequential part_index and total_parts=3."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/multi.pdf",
        {"multi.pdf": _make_pdf_bytes_multi_page(["# Chapter A", "# Chapter B", "# Chapter C"])},
    )
    assert len(parts) == 3
    for index, part in enumerate(parts, start=1):
        docline = part["frontmatter"]["docline"]
        assert docline["part_index"] == index
        assert docline["total_parts"] == 3


def test_multi_part_output_prev_next_chain(tmp_path: Path) -> None:
    """Three-H1 PDF yields a connected prev/next chain across the three parts."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/chain.pdf",
        {"chain.pdf": _make_pdf_bytes_multi_page(["# A", "# B", "# C"])},
    )
    assert len(parts) == 3
    docline0 = parts[0]["frontmatter"]["docline"]
    docline1 = parts[1]["frontmatter"]["docline"]
    docline2 = parts[2]["frontmatter"]["docline"]
    assert docline0["prev_part"] is None
    assert docline0["next_part"] == "part-0002.md"
    assert docline1["prev_part"] == "part-0001.md"
    assert docline1["next_part"] == "part-0003.md"
    assert docline2["prev_part"] == "part-0002.md"
    assert docline2["next_part"] is None


def test_parts_share_parent_document_id(tmp_path: Path) -> None:
    """All parts produced from a single source share the same parent_document_id."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/shared.pdf",
        {"shared.pdf": _make_pdf_bytes_multi_page(["# One", "# Two", "# Three"])},
    )
    assert len(parts) == 3
    parent_ids = {part["frontmatter"]["docline"]["parent_document_id"] for part in parts}
    assert len(parent_ids) == 1, f"expected single parent_document_id, got {parent_ids}"


def test_parent_document_id_deterministic_for_same_input(tmp_path: Path) -> None:
    """Running process twice on the same source yields the same parent_document_id (deterministic)."""  # noqa: E501
    pdf = _make_pdf_bytes_multi_page(["# Det A", "# Det B"])
    run_a = _process_and_load_parts(tmp_path / "a", "local_file:docs/det.pdf", {"det.pdf": pdf})
    run_b = _process_and_load_parts(tmp_path / "b", "local_file:docs/det.pdf", {"det.pdf": pdf})
    id_a = run_a[0]["frontmatter"]["docline"]["parent_document_id"]
    id_b = run_b[0]["frontmatter"]["docline"]["parent_document_id"]
    assert id_a == id_b


def test_section_title_populated_when_h1_present(tmp_path: Path) -> None:
    """When a part starts at an H1 boundary, docline.section_title matches the H1 text."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/sections.pdf",
        {"sections.pdf": _make_pdf_bytes_multi_page(["# Introduction", "# Methods", "# Results"])},
    )
    assert len(parts) == 3
    titles = [part["frontmatter"]["docline"]["section_title"] for part in parts]
    assert titles == ["Introduction", "Methods", "Results"]


def test_section_title_null_for_char_bin_fallback(tmp_path: Path) -> None:
    """Flat-text PDF with no H1 produces a single part with docline.section_title=None."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/flat.pdf",
        {
            "flat.pdf": _make_pdf_bytes_multi_page(
                ["Page one text", "Page two text", "Page three text"]
            )
        },
    )
    assert len(parts) == 1
    assert parts[0]["frontmatter"]["docline"]["section_title"] is None


def test_chunk_anchors_emitted_by_default_in_processed_output(tmp_path: Path) -> None:
    """Processed output bodies contain ``<a id="chunk-NNNN"></a>`` anchors before headings by default."""  # noqa: E501
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/anchored.pdf",
        {"anchored.pdf": _make_pdf_bytes_multi_page(["# Heading One", "# Heading Two"])},
    )
    assert len(parts) == 2
    for part in parts:
        assert '<a id="chunk-0001"></a>' in part["body"]


def test_chunk_anchors_skip_fenced_code_in_processed_output(tmp_path: Path) -> None:
    """Headings inside fenced code blocks do not receive chunk anchors in processed output.

    DOCX doesn't easily encode fenced code from a minimal fixture; this test
    uses a `.md` source which is passed through `execute_process` unchanged
    by the segmenter (HTML/MD/TXT branch) but still routed through the
    `assemble_markdown` call that now defaults `emit_chunk_anchors=True`.
    """
    md_body = (
        "# Real Heading\n\n"
        "Some prose.\n\n"
        "```python\n"
        "# This is NOT a markdown heading inside a fence\n"
        "print('hello')\n"
        "```\n"
    )
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/fenced.md",
        {"fenced.md": md_body.encode("utf-8")},
    )
    assert len(parts) == 1
    body = parts[0]["body"]
    assert '<a id="chunk-0001"></a>' in body
    assert body.count('<a id="chunk-') == 1, (
        "expected exactly one chunk anchor; heading inside fenced code should be skipped"
    )


def test_docline_namespace_serializes_to_frontmatter_yaml(tmp_path: Path) -> None:
    """The docline: block appears as a nested YAML map in every emitted .md frontmatter."""
    parts = _process_and_load_parts(
        tmp_path,
        "local_file:docs/yaml.docx",
        {"yaml.docx": _make_minimal_docx()},
    )
    assert len(parts) == 1
    raw = parts[0]["path"].read_text(encoding="utf-8")
    _, fm_block, _ = raw.split("---", 2)
    assert "docline:" in fm_block
    assert "parent_document_id:" in fm_block
    assert "part_index:" in fm_block
    assert "total_parts:" in fm_block
