"""Failing-first tests for media-sidecar surfacing in manifest (G3c task 015.001-T).

End-to-end coverage that ``execute_process`` extracts DOCX embedded images
to ``{output_root}/{job_id}/{source_basename}/media/figure-NNNN.ext`` and
surfaces every extracted artifact as ``media_files`` in the per-source
manifest entry.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source

# 1x1 PNG (8-byte sig + IHDR + IDAT + IEND, valid)
_MIN_PNG = bytes.fromhex(
    "89504e470d0a1a0a"
    "0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c63000100000005000119d9d7720000000049454e44ae426082"
)


def _write_staging_job(staging_root: Path, source_key: str, files: dict[str, bytes]) -> StagingJob:
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


def _make_docx_with_one_image() -> bytes:
    """Return a minimal DOCX with one paragraph and one embedded PNG."""
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_pic = "http://schemas.openxmlformats.org/drawingml/2006/picture"
    document_xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns_w}">'
        "<w:body>"
        f'<w:p xmlns:r="{ns_r}" xmlns:a="{ns_a}" xmlns:pic="{ns_pic}">'
        "<w:r><w:t>An image follows</w:t></w:r>"
        '<w:r><w:drawing><a:graphic><a:graphicData uri="">'
        '<pic:pic><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill></pic:pic>'
        "</a:graphicData></a:graphic></w:drawing></w:r>"
        "</w:p>"
        "</w:body></w:document>"
    )
    rels_xml = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/>'
        "</Relationships>"
    )
    package_rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    types_xml = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types_xml)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        zf.writestr("word/media/image1.png", _MIN_PNG)
    return buf.getvalue()


def _make_pdf_bytes_single_page(text: str) -> bytes:
    """Return minimal single-page PDF with one text stream (no headings)."""
    content_stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            b" /Contents 4 0 R >>\nendobj\n"
        ),
        (
            f"4 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    return b"%PDF-1.4\n" + b"".join(objects) + b"%%EOF\n"


def _make_html_bytes(body: str) -> bytes:
    """Return a minimal HTML file body."""
    return f"<html><body>{body}</body></html>".encode()


def _run_process(tmp_path: Path, source_key: str, files: dict[str, bytes]) -> tuple[Path, dict]:
    """Execute the process pipeline and return (job_root, manifest_dict)."""
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
    assert result.success, f"process failed: {result.error}"
    job_root = output_dir / job.job_id
    manifest = json.loads((job_root / "manifest.json").read_text(encoding="utf-8"))
    return job_root, manifest


def test_docx_image_sidecar_written_to_media_root(tmp_path: Path) -> None:
    """A DOCX with one embedded image produces a sidecar PNG on disk.

    The sidecar lands under the source's per-source media root
    (``{job_id}/{source_basename}/media/figure-0001.png``).
    """
    job_root, _ = _run_process(
        tmp_path,
        "local_file:docs/report.docx",
        {"report.docx": _make_docx_with_one_image()},
    )
    sidecar = job_root / "report" / "media" / "figure-0001.png"
    assert sidecar.is_file(), f"expected sidecar at {sidecar}"
    assert sidecar.read_bytes() == _MIN_PNG


def test_manifest_entry_includes_media_files_relative_paths(tmp_path: Path) -> None:
    """The per-source manifest entry lists the sidecar paths relative to ``{job_id}/``."""
    _job_root, manifest = _run_process(
        tmp_path,
        "local_file:docs/with-image.docx",
        {"with-image.docx": _make_docx_with_one_image()},
    )
    docs = manifest["documents"]
    assert len(docs) == 1
    assert docs[0].get("media_files") == ["with-image/media/figure-0001.png"]


def test_pdf_without_docling_produces_empty_media_files(tmp_path: Path) -> None:
    """Flat PDF processed without the docling extra carries ``media_files: []``."""
    _job_root, manifest = _run_process(
        tmp_path,
        "local_file:docs/flat.pdf",
        {"flat.pdf": _make_pdf_bytes_single_page("flat content")},
    )
    docs = manifest["documents"]
    assert len(docs) == 1
    assert docs[0].get("media_files") == []


def test_html_source_has_empty_media_files(tmp_path: Path) -> None:
    """HTML branch carries ``media_files: []`` (image-extraction is DOCX/PDF only)."""
    _job_root, manifest = _run_process(
        tmp_path,
        "local_file:docs/page.html",
        {"page.html": _make_html_bytes("<h1>Hi</h1>")},
    )
    docs = manifest["documents"]
    assert len(docs) == 1
    assert docs[0].get("media_files") == []


def test_outputs_without_media_omit_media_root_dir(tmp_path: Path) -> None:
    """Sources with no extracted media do not create an empty ``media/`` directory."""
    job_root, _ = _run_process(
        tmp_path,
        "local_file:docs/flat.pdf",
        {"flat.pdf": _make_pdf_bytes_single_page("nothing to extract")},
    )
    # No media root anywhere under the job root.
    assert not any(p.name == "media" and p.is_dir() for p in job_root.rglob("*"))
