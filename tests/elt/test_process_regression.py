"""Regression tests for four concrete gaps found in real .elt sample runs.

Covers:
1. GitHub **/*.md glob matches top-level markdown files (tested in
   test_github_reader.py; cross-referenced here via execute_elt_fetch).
2. Output paths are unique per staging job — two URL sources do NOT
   overwrite each other's page.md output.
3. Processed output files contain YAML frontmatter (--- delimiters).
4. PDF hex strings containing UTF-16BE-encoded text decode to readable
   text rather than NUL-separated gibberish.
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docline.app import _extract_source_url
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _write_staging_job(
    staging_root: Path,
    source_key: str,
    files: dict[str, bytes],
    complete: bool = True,
) -> StagingJob:
    """Write a staging job with content files on disk.

    Args:
        staging_root: Root staging directory.
        source_key: Source key for job ID generation.
        files: Mapping of filename → file bytes to write.
        complete: Whether the job is marked complete.

    Returns:
        The created StagingJob.
    """
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

    metadata = SourceMetadata(
        source=sanitize_source(source_key),
        fetch_timestamp=datetime.now(UTC),
    )
    job = StagingJob(
        job_id=job_id,
        metadata=metadata,
        cache_path=cache_rel,
        complete=complete,
    )
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job


def _make_minimal_docx() -> bytes:
    """Return minimal valid DOCX bytes with 'Hello DOCX' text."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns}">'
        "<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
    return buf.getvalue()


def _make_pdf_with_utf16be_hex(text: str) -> bytes:
    """Return PDF bytes where the text is embedded as a UTF-16BE hex string.

    Args:
        text: Plain text to encode as UTF-16BE in a PDF hex string.

    Returns:
        Raw PDF bytes with the text in a <hexstring> Tj operator.
    """
    utf16_bytes = text.encode("utf-16-be")
    hex_str = utf16_bytes.hex().upper()
    content_stream = f"BT /F1 12 Tf 100 700 Td <{hex_str}> Tj ET"
    stream_bytes = content_stream.encode("ascii")
    length = len(stream_bytes)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode() + b" >>\n"
        b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
        b"%%EOF\n"
    )


def _make_pdf_with_utf16be_literal(text: str) -> bytes:
    """Return PDF bytes where the text is embedded as a UTF-16BE literal string.

    The literal string uses the UTF-16BE BOM (\\xfe\\xff) prefix so that
    the reader can identify the encoding.

    Args:
        text: Plain text to embed as a UTF-16BE PDF literal string.

    Returns:
        Raw PDF bytes with the text in a (string) Tj operator.
    """
    # UTF-16BE with BOM
    raw_bytes = b"\xfe\xff" + text.encode("utf-16-be")
    # PDF literal escape: parentheses and backslashes only
    escaped = raw_bytes.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    content_stream = b"BT /F1 12 Tf 100 700 Td (" + escaped + b") Tj ET"
    length = len(content_stream)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode() + b" >>\n"
        b"stream\n" + content_stream + b"\nendstream\nendobj\n"
        b"%%EOF\n"
    )


# ---------------------------------------------------------------------------
# Issue 4: PDF UTF-16 decoding
# ---------------------------------------------------------------------------


class TestPdfUtf16Decoding:
    """PDF hex strings with UTF-16BE encoding must decode to readable text."""

    def test_hex_string_utf16be_decodes_without_nul_chars(self, tmp_path: Path) -> None:
        """A PDF with UTF-16BE hex content produces text without NUL separators."""
        from docline.readers.pdf import read_pdf

        pdf_bytes = _make_pdf_with_utf16be_hex("Hello Azure")
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_bytes)

        result = read_pdf(pdf_path)

        assert "\x00" not in result, "Result must not contain NUL characters"
        assert "Hello Azure" in result

    def test_hex_string_utf16be_no_bom_decodes_by_heuristic(self, tmp_path: Path) -> None:
        """UTF-16BE hex without BOM is detected by NUL-interleave heuristic."""
        from docline.readers.pdf import read_pdf

        # Encode without BOM — pure UTF-16BE bytes
        text = "CosmosDB"
        utf16_bytes = text.encode("utf-16-be")  # no BOM
        hex_str = utf16_bytes.hex().upper()
        content_stream = f"BT /F1 12 Tf 100 700 Td <{hex_str}> Tj ET"
        stream_bytes = content_stream.encode("ascii")
        length = len(stream_bytes)
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            b" /Contents 4 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Length " + str(length).encode() + b" >>\n"
            b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
            b"%%EOF\n"
        )

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_bytes)

        result = read_pdf(pdf_path)

        assert "\x00" not in result
        assert "CosmosDB" in result

    def test_literal_string_utf16be_bom_decodes_readable(self, tmp_path: Path) -> None:
        """A PDF literal string with UTF-16BE BOM decodes to readable text."""
        from docline.readers.pdf import read_pdf

        pdf_bytes = _make_pdf_with_utf16be_literal("Azure Cosmos")
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_bytes)

        result = read_pdf(pdf_path)

        assert "\x00" not in result
        assert "Azure Cosmos" in result


# ---------------------------------------------------------------------------
# Issue 2: Unique output paths
# ---------------------------------------------------------------------------


class TestUniqueOutputPaths:
    """Two staged URL sources must produce separate output files."""

    def test_two_url_sources_produce_separate_output_files(self, tmp_path: Path) -> None:
        """execute_process writes distinct output files for two different URL jobs."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        # Two separate URL jobs — each has a page.html in its own files/ dir
        _write_staging_job(
            staging_dir,
            "web_crawl:https://example.com/docs",
            {"page.html": b"<html><body><h1>Docs page</h1></body></html>"},
        )
        _write_staging_job(
            staging_dir,
            "web_crawl:https://example.com/api",
            {"page.html": b"<html><body><h1>API page</h1></body></html>"},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) == 2, f"Expected 2 output files, got {len(md_files)}: {md_files}"

    def test_two_local_sources_with_same_filename_produce_separate_outputs(
        self, tmp_path: Path
    ) -> None:
        """Two jobs with a file named the same must not overwrite each other."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/alpha/report.pdf",
            {"report.pdf": _make_pdf_bytes_simple("Alpha report content")},
        )
        _write_staging_job(
            staging_dir,
            "local_file:docs/beta/report.pdf",
            {"report.pdf": _make_pdf_bytes_simple("Beta report content")},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) == 2, f"Expected 2 separate outputs, got {len(md_files)}: {md_files}"

    def test_processing_failure_without_outputs_leaves_output_path_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """execute_process leaves output_path unset when no output file is written."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/broken.docx",
            {"broken.docx": _make_minimal_docx()},
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        def _raise_build_error(*_args: object, **_kwargs: object) -> list[object]:
            raise RuntimeError("boom")

        monkeypatch.setattr("docline.app.build_output_document_parts", _raise_build_error)

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(original_cwd)

        assert result.success is False
        assert result.output_path is None
        assert result.error == "boom"

    def test_completed_job_with_no_outputs_returns_failure(self, tmp_path: Path) -> None:
        """execute_process fails when a completed staging job yields no outputs."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/empty",
            {},
        )

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

        assert result.success is False
        assert result.output_path is None
        assert result.error == "Completed staging jobs produced no processed outputs."


def test_extract_source_url_strips_legacy_web_crawl_suffixes() -> None:
    """Legacy web crawl suffixes are excluded from extracted source URLs."""
    source = "web_crawl:https://example.com/docs:depth=3:max_pages=25"

    assert _extract_source_url(source) == "https://example.com/docs"


def _make_pdf_bytes_simple(text: str) -> bytes:
    """Create a minimal PDF with plain-ASCII text in a literal string."""
    content_stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")
    length = len(stream_bytes)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode() + b" >>\n"
        b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
        b"%%EOF\n"
    )


def _make_pdf_bytes_multi_page(texts: list[str]) -> bytes:
    """Create a minimal multi-page PDF with one text stream per page."""
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


# ---------------------------------------------------------------------------
# Issue 3: YAML frontmatter in output
# ---------------------------------------------------------------------------


class TestOutputHasFrontmatter:
    """Processed output files must contain valid YAML frontmatter."""

    def test_docx_output_starts_with_yaml_frontmatter(self, tmp_path: Path) -> None:
        """execute_process emits YAML frontmatter block in DOCX output."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/sample.docx",
            {"sample.docx": _make_minimal_docx()},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert md_files, "No output markdown files were created"
        content = md_files[0].read_text(encoding="utf-8")
        assert content.startswith("---\n"), "Output must start with YAML frontmatter delimiter"
        # Frontmatter must close
        second_delim = content.find("---\n", 4)
        assert second_delim != -1, "Output must contain a closing --- delimiter"

    def test_html_output_has_web_frontmatter_doc_type(self, tmp_path: Path) -> None:
        """execute_process emits doc_type: web in frontmatter for URL-sourced HTML."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "web_crawl:https://docs.example.com/page",
            {"page.html": b"<html><body><h1>Example Doc</h1></body></html>"},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert md_files
        content = md_files[0].read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert '"web"' in content or "web" in content.split("---")[1]

    def test_html_output_uses_per_page_source_url_and_crawl_depth(self, tmp_path: Path) -> None:
        """execute_process prefers staged per-page metadata for crawled HTML files."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        job = _write_staging_job(
            staging_dir,
            "manifest_url:docs:https://docs.example.com/start/",
            {"guides/index.html": b"<html><body><h1>Guide</h1></body></html>"},
        )
        cache_abs = staging_dir.parent / job.cache_path
        meta_path = cache_abs / "files" / "guides" / "index.meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "page_url": "https://docs.example.com/guides/",
                    "crawl_depth": 2,
                }
            ),
            encoding="utf-8",
        )

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

        assert result.success is True
        output_path = output_dir / job.job_id / "guides" / "index.md"
        assert output_path.is_file()
        content = output_path.read_text(encoding="utf-8")
        frontmatter_block = content.split("---")[1]
        assert "source_url" in frontmatter_block
        assert "https://docs.example.com/guides/" in frontmatter_block
        assert "crawl_depth: 2" in frontmatter_block

    def test_html_outputs_follow_crawl_manifest_order_in_root_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        """execute_process writes web manifest entries in crawl order, not alpha order."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        job = _write_staging_job(
            staging_dir,
            "manifest_url:docs:https://docs.example.com/start/",
            {
                "zebra.html": b"<html><body><h1>Zebra</h1></body></html>",
                "aardvark.html": b"<html><body><h1>Aardvark</h1></body></html>",
                "mango.html": b"<html><body><h1>Mango</h1></body></html>",
            },
        )
        cache_abs = staging_dir.parent / job.cache_path
        files_dir = cache_abs / "files"
        metadata_by_file = {
            "zebra.html": {
                "page_url": "https://docs.example.com/zebra",
                "crawl_depth": 0,
                "crawl_order": 0,
            },
            "mango.html": {
                "page_url": "https://docs.example.com/mango",
                "crawl_depth": 1,
                "crawl_order": 1,
            },
            "aardvark.html": {
                "page_url": "https://docs.example.com/aardvark",
                "crawl_depth": 2,
                "crawl_order": 2,
            },
        }
        for name, payload in metadata_by_file.items():
            (files_dir / name).with_suffix(".meta.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
        (cache_abs / "crawl-manifest.json").write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "crawl_order": 0,
                            "relative_path": "zebra.html",
                            **metadata_by_file["zebra.html"],
                        },
                        {
                            "crawl_order": 1,
                            "relative_path": "mango.html",
                            **metadata_by_file["mango.html"],
                        },
                        {
                            "crawl_order": 2,
                            "relative_path": "aardvark.html",
                            **metadata_by_file["aardvark.html"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

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

        assert result.success is True
        manifest_data = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        documents = manifest_data["documents"]
        assert [doc["input_file"] for doc in documents] == [
            "zebra.html",
            "mango.html",
            "aardvark.html",
        ]
        assert [doc["crawl_order"] for doc in documents] == [0, 1, 2]
        assert [doc["crawl_depth"] for doc in documents] == [0, 1, 2]
        assert [doc["source_url"] for doc in documents] == [
            "https://docs.example.com/zebra",
            "https://docs.example.com/mango",
            "https://docs.example.com/aardvark",
        ]
        source_manifest = json.loads(
            (output_dir / job.job_id / "manifest.json").read_text(encoding="utf-8")
        )
        source_documents = source_manifest["documents"]
        assert [doc["input_file"] for doc in source_documents] == [
            "zebra.html",
            "mango.html",
            "aardvark.html",
        ]
        assert [doc["input_path"] for doc in source_documents] == [
            "zebra.html",
            "mango.html",
            "aardvark.html",
        ]
        assert [doc["ingest_order"] for doc in source_documents] == [0, 1, 2]
        assert [doc["output_path"] for doc in source_documents] == [
            "zebra.md",
            "mango.md",
            "aardvark.md",
        ]
        assert all("document_id" in doc for doc in source_documents)

    def test_html_output_has_consistent_h1_root_for_crawled_pages(self, tmp_path: Path) -> None:
        """execute_process wraps web pages so each file starts with a stable H1 root."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        job = _write_staging_job(
            staging_dir,
            "manifest_url:docs:https://docs.example.com/start/",
            {"guide.html": b"<html><body><h2>Section</h2><h4>Nested</h4></body></html>"},
        )
        cache_abs = staging_dir.parent / job.cache_path
        (cache_abs / "files" / "guide.meta.json").write_text(
            json.dumps(
                {
                    "page_url": "https://docs.example.com/guide",
                    "crawl_depth": 0,
                    "crawl_order": 0,
                }
            ),
            encoding="utf-8",
        )

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

        assert result.success is True
        output_path = output_dir / job.job_id / "guide.md"
        content = output_path.read_text(encoding="utf-8")
        body = content.split("---\n", 2)[2]
        assert body.startswith("# Guide\n\n## Section\n\n### Nested\n")

    def test_local_pdf_output_has_wiki_frontmatter_doc_type(self, tmp_path: Path) -> None:
        """execute_process emits doc_type: wiki in frontmatter for local PDF sources."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/cosmos.pdf",
            {"cosmos.pdf": _make_pdf_bytes_simple("Azure CosmosDB documentation")},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert md_files
        content = md_files[0].read_text(encoding="utf-8")
        assert content.startswith("---\n")
        frontmatter_block = content.split("---")[1]
        assert "wiki" in frontmatter_block

    def test_frontmatter_contains_required_fields(self, tmp_path: Path) -> None:
        """YAML frontmatter must contain title, source, ingested_at, doc_type."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _write_staging_job(
            staging_dir,
            "local_file:docs/guide.docx",
            {"guide.docx": _make_minimal_docx()},
        )

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

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert md_files
        content = md_files[0].read_text(encoding="utf-8")
        frontmatter_block = content.split("---")[1]
        assert "title:" in frontmatter_block
        assert "source:" in frontmatter_block
        assert "ingested_at:" in frontmatter_block
        assert "doc_type:" in frontmatter_block

    def test_multi_page_pdf_output_is_segmented_with_standardized_manifest_fields(
        self, tmp_path: Path
    ) -> None:
        """Large PDF sources emit ordered multi-file output instead of one giant markdown file."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        job = _write_staging_job(
            staging_dir,
            "local_file:docs/segmented-report.pdf",
            {
                "segmented-report.pdf": _make_pdf_bytes_multi_page(
                    ["Page one summary", "Page two details", "Page three appendix"]
                )
            },
        )

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

        assert result.success is True
        source_manifest = json.loads(
            (output_dir / job.job_id / "manifest.json").read_text(encoding="utf-8")
        )
        source_documents = source_manifest["documents"]
        assert [doc["input_path"] for doc in source_documents] == [
            "segmented-report.pdf",
            "segmented-report.pdf",
            "segmented-report.pdf",
        ]
        assert [doc["ingest_order"] for doc in source_documents] == [0, 1, 2]
        assert [doc["output_path"] for doc in source_documents] == [
            str(Path("segmented-report") / "part-0001.md"),
            str(Path("segmented-report") / "part-0002.md"),
            str(Path("segmented-report") / "part-0003.md"),
        ]
        assert all("document_id" in doc for doc in source_documents)
        assert not (output_dir / job.job_id / "segmented-report.md").exists()
        assert "Page one summary" in (
            output_dir / job.job_id / "segmented-report" / "part-0001.md"
        ).read_text(encoding="utf-8")
