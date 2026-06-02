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
import zipfile
from datetime import UTC, datetime
from pathlib import Path

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
