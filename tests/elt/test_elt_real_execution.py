"""End-to-end ELT execution tests covering fetch+process for local and remote sources.

Tests cover:
- execute_elt_fetch with local DOCX and PDF sources
- execute_elt_fetch with mocked URL and GitHub sources
- execute_process with staged DOCX and PDF content
- CLI/app process success path
"""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from docline.fetch.models import SourceMetadata, StagingJob


def _make_staging_job(
    staging_dir: Path,
    source_key: str,
    files: dict[str, bytes],
    complete: bool = True,
) -> StagingJob:
    """Create a staging job with content files on disk for testing.

    Args:
        staging_dir: Root staging directory.
        source_key: Source key for job ID generation.
        files: Mapping of filename → file bytes to write.
        complete: Whether the job is marked complete.

    Returns:
        The created StagingJob.
    """
    from datetime import UTC, datetime

    from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source

    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(str(staging_dir.name), job_id)
    cache_abs = staging_dir.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    for name, content in files.items():
        (files_dir / name).write_bytes(content)

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
    """Create a minimal valid DOCX with 'Hello World' content.

    Returns:
        DOCX file bytes.
    """
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns}">'
        "<w:body><w:p><w:r>"
        "<w:t>Hello World from DOCX</w:t>"
        "</w:r></w:p></w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
    return buf.getvalue()


def _make_minimal_pdf_with_text(text: str) -> bytes:
    """Create a minimal PDF with literal text in an uncompressed content stream.

    Args:
        text: Text to embed in the PDF.

    Returns:
        PDF file bytes.
    """
    content_stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")
    length = len(stream_bytes)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode() + b" >>\n"
        b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
        b"%%EOF\n"
    )
    return pdf


# ---------------------------------------------------------------------------
# execute_elt_fetch: local sources
# ---------------------------------------------------------------------------


class TestEltFetchLocalDocx:
    """execute_elt_fetch stages local DOCX files correctly."""

    def test_local_docx_source_staged_to_files_dir(self, tmp_path: Path) -> None:
        """execute_elt_fetch copies a local DOCX into the staging files directory."""
        from docline.elt.execute import execute_elt_fetch

        # Create a DOCX file in the workspace
        docx_path = tmp_path / "docs" / "sample.docx"
        docx_path.parent.mkdir()
        docx_path.write_bytes(_make_minimal_docx())

        # Write a flat-format local_file config
        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "local.yaml").write_text(
            "type: local_file\npaths:\n  - docs/sample.docx\n", encoding="utf-8"
        )

        staging_dir = ".elt/staging"
        jobs = execute_elt_fetch(config_dir, staging_dir, workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        # Files should be staged
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("*.docx"))
        assert len(staged_files) == 1

    def test_manifest_local_docx_source_staged_with_path_heuristic(self, tmp_path: Path) -> None:
        """execute_elt_fetch applies the tmp→.elt path heuristic for manifest sources."""
        from docline.elt.execute import execute_elt_fetch

        # Create DOCX under .elt/ (the current workspace layout)
        elt_dir = tmp_path / ".elt"
        elt_dir.mkdir()
        docx_path = elt_dir / "SampleDoc.docx"
        docx_path.write_bytes(_make_minimal_docx())

        # Manifest source uses the stale 'tmp' path
        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir()
        (config_dir / "docs.sources.yaml").write_text(
            (
                "sources:\n"
                "  - id: my-docx\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "**/*.docx"\n'
            ),
            encoding="utf-8",
        )

        jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("*.docx"))
        assert len(staged_files) >= 1


class TestEltFetchLocalPdf:
    """execute_elt_fetch stages local PDF files correctly."""

    def test_local_pdf_source_staged_to_files_dir(self, tmp_path: Path) -> None:
        """execute_elt_fetch copies a local PDF into the staging files directory."""
        from docline.elt.execute import execute_elt_fetch

        pdf_path = tmp_path / "docs" / "report.pdf"
        pdf_path.parent.mkdir()
        pdf_path.write_bytes(_make_minimal_pdf_with_text("PDF content here"))

        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "local.yaml").write_text(
            "type: local_file\npaths:\n  - docs/report.pdf\n", encoding="utf-8"
        )

        jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("*.pdf"))
        assert len(staged_files) == 1

    def test_manifest_local_pdf_source_staged_with_cosmos_pattern(self, tmp_path: Path) -> None:
        """execute_elt_fetch stages a specific PDF named in include."""
        from docline.elt.execute import execute_elt_fetch

        elt_dir = tmp_path / ".elt"
        elt_dir.mkdir()
        (elt_dir / "azure-cosmos-db.pdf").write_bytes(
            _make_minimal_pdf_with_text("CosmosDB content")
        )

        config_dir = elt_dir / "config"
        config_dir.mkdir()
        (config_dir / "cosmosdb.sources.yaml").write_text(
            (
                "sources:\n"
                "  - id: cosmos-db\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "azure-cosmos-db.pdf"\n'
                "    formats: [pdf]\n"
                '    database: "cosmos.db"\n'
            ),
            encoding="utf-8",
        )

        jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("azure-cosmos-db.pdf"))
        assert len(staged_files) == 1


class TestEltFetchUrlSource:
    """execute_elt_fetch handles URL sources (with mocked HTTP)."""

    def test_url_source_staged_as_html(self, tmp_path: Path) -> None:
        """execute_elt_fetch writes fetched HTML to staging files dir."""
        from docline.elt.execute import execute_elt_fetch
        from docline.fetch.crawl import CrawlResult
        from docline.fetch.http import FetchResponse

        mock_response = FetchResponse(
            url="https://example.com",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Hello</h1><p>World</p></body></html>",
        )
        mock_result = CrawlResult(url="https://example.com", response=mock_response)

        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "web.sources.yaml").write_text(
            ("sources:\n  - id: example-site\n    type: url\n    url: https://example.com\n"),
            encoding="utf-8",
        )

        async def fake_crawl(start_url: str, config=None):
            del start_url, config
            return [mock_result]

        with patch("docline.fetch.crawl.crawl", side_effect=fake_crawl):
            jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("page.html"))
        assert len(staged_files) == 1
        assert "Hello" in staged_files[0].read_text(encoding="utf-8")

    def test_url_fetch_failure_marks_job_incomplete(self, tmp_path: Path) -> None:
        """execute_elt_fetch marks a job incomplete when the URL fetch fails."""
        from docline.elt.execute import execute_elt_fetch

        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "web.yaml").write_text(
            "type: web_crawl\nurl: https://example.com\n", encoding="utf-8"
        )

        async def fake_crawl(start_url: str, config=None):
            del start_url, config
            raise OSError("Network down")

        with patch("docline.fetch.crawl.crawl", side_effect=fake_crawl):
            jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is False

    def test_url_source_stages_multiple_pages_with_metadata(self, tmp_path: Path) -> None:
        """execute_elt_fetch stages every crawled page plus per-page metadata."""
        from docline.elt.execute import execute_elt_fetch
        from docline.fetch.crawl import CrawlResult
        from docline.fetch.http import FetchResponse

        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "web.sources.yaml").write_text(
            (
                "sources:\n"
                "  - id: example-site\n"
                "    type: url\n"
                "    url: https://example.com/docs/\n"
                "    max_depth: 1\n"
                "    max_pages: 5\n"
            ),
            encoding="utf-8",
        )

        crawl_results = [
            CrawlResult(
                url="https://example.com/docs/",
                depth=0,
                response=FetchResponse(
                    url="https://example.com/docs/",
                    status=200,
                    content_type="text/html",
                    body="<html><body><h1>Docs Home</h1></body></html>",
                ),
            ),
            CrawlResult(
                url="https://example.com/docs/getting-started/",
                depth=1,
                response=FetchResponse(
                    url="https://example.com/docs/getting-started/",
                    status=200,
                    content_type="text/html",
                    body="<html><body><h1>Getting Started</h1></body></html>",
                ),
            ),
        ]

        async def fake_crawl(start_url: str, config=None):
            del start_url, config
            return crawl_results

        with patch("docline.fetch.crawl.crawl", side_effect=fake_crawl):
            jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        assert (cache_abs / "files" / "page.html").is_file()
        assert (cache_abs / "files" / "page.meta.json").is_file()
        assert (cache_abs / "files" / "docs" / "getting-started" / "index.html").is_file()
        metadata_path = cache_abs / "files" / "docs" / "getting-started" / "index.meta.json"
        assert metadata_path.is_file()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["page_url"] == "https://example.com/docs/getting-started/"
        assert metadata["crawl_depth"] == 1
        assert metadata["crawl_order"] == 1
        crawl_manifest_path = cache_abs / "crawl-manifest.json"
        assert crawl_manifest_path.is_file()
        crawl_manifest = json.loads(crawl_manifest_path.read_text(encoding="utf-8"))
        assert crawl_manifest["pages"] == [
            {
                "crawl_order": 0,
                "relative_path": "page.html",
                "page_url": "https://example.com/docs/",
                "crawl_depth": 0,
            },
            {
                "crawl_order": 1,
                "relative_path": "docs/getting-started/index.html",
                "page_url": "https://example.com/docs/getting-started/",
                "crawl_depth": 1,
            },
        ]


class TestEltFetchGitHubSource:
    """execute_elt_fetch handles GitHub manifest sources (with mocked HTTP)."""

    def test_github_source_staged_as_markdown_files(self, tmp_path: Path) -> None:
        """execute_elt_fetch writes fetched GitHub files to staging."""
        from docline.elt.execute import execute_elt_fetch

        config_dir = tmp_path / ".elt" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "git.sources.yaml").write_text(
            (
                "sources:\n"
                "  - id: fabric-specs\n"
                "    type: git\n"
                "    url: https://github.com/microsoft/fabric-rest-api-specs.git\n"
                "    branch: main\n"
                "    include:\n"
                '      - "**/*.md"\n'
            ),
            encoding="utf-8",
        )

        mock_files = [("README.md", "# Fabric REST API Specs\n\nContent here.")]
        with patch("docline.elt.execute.fetch_github_files", return_value=mock_files):
            jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].complete is True
        cache_abs = tmp_path / jobs[0].cache_path
        staged_files = list((cache_abs / "files").rglob("*.md"))
        assert len(staged_files) == 1
        assert "Fabric" in staged_files[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# execute_process: staged content → markdown output
# ---------------------------------------------------------------------------


class TestExecuteProcessDocx:
    """execute_process converts staged DOCX to markdown output."""

    def test_staged_docx_produces_markdown_file(self, tmp_path: Path) -> None:
        """execute_process writes a markdown file for a staged DOCX."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _make_staging_job(
            staging_dir,
            "local_file:docs/sample.docx",
            {"sample.docx": _make_minimal_docx()},
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(original_cwd)

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "Hello World from DOCX" in content

    def test_staged_docx_produces_manifest_json(self, tmp_path: Path) -> None:
        """execute_process writes a manifest.json in the output directory."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _make_staging_job(
            staging_dir,
            "local_file:docs/sample.docx",
            {"sample.docx": _make_minimal_docx()},
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True
        manifest_path = output_dir / "manifest.json"
        assert manifest_path.exists()
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "documents" in manifest_data
        assert manifest_data["documents"][0]["input_path"] == "sample.docx"
        assert manifest_data["documents"][0]["ingest_order"] == 0
        assert "document_id" in manifest_data["documents"][0]


class TestExecuteProcessPdf:
    """execute_process converts staged PDF to markdown output."""

    def test_staged_pdf_produces_markdown_file(self, tmp_path: Path) -> None:
        """execute_process writes a markdown file for a staged PDF with text."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        pdf_content = _make_minimal_pdf_with_text("Azure documentation content")
        staging_dir = tmp_path / "staging"
        _make_staging_job(
            staging_dir,
            "local_file:docs/report.pdf",
            {"report.pdf": pdf_content},
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1


class TestExecuteProcessEmptyStaging:
    """execute_process handles edge cases gracefully."""

    def test_empty_staging_dir_returns_success(self, tmp_path: Path) -> None:
        """execute_process succeeds with an empty staging directory."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        output_dir = tmp_path / "output"

        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True

    def test_incomplete_staging_jobs_are_skipped(self, tmp_path: Path) -> None:
        """execute_process skips staging jobs with complete=False."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        staging_dir = tmp_path / "staging"
        _make_staging_job(
            staging_dir,
            "web_crawl:https://example.com",
            {"page.html": b"<html><body>content</body></html>"},
            complete=False,  # job is NOT complete
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True
        # No markdown files should be written for incomplete jobs
        md_files = list(output_dir.rglob("*.md")) if output_dir.exists() else []
        assert len(md_files) == 0


class TestExecuteProcessHtml:
    """execute_process converts staged HTML to markdown output."""

    def test_staged_html_produces_markdown_file(self, tmp_path: Path) -> None:
        """execute_process converts staged HTML to markdown via extraction."""
        from docline.app import execute_process
        from docline.app_models import ProcessRequest

        html_content = b"<html><body><h1>Test Page</h1><p>Content paragraph.</p></body></html>"
        staging_dir = tmp_path / "staging"
        _make_staging_job(
            staging_dir,
            "web_crawl:https://example.com",
            {"page.html": html_content},
        )

        output_dir = tmp_path / "output"
        request = ProcessRequest(
            staging_dir=str(staging_dir.relative_to(tmp_path)),
            output_dir=str(output_dir.relative_to(tmp_path)),
        )

        import os

        try:
            os.chdir(tmp_path)
            result = execute_process(request)
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "Test Page" in content


# ---------------------------------------------------------------------------
# Metadata.json round-trip
# ---------------------------------------------------------------------------


class TestStagingMetadataRoundTrip:
    """execute_elt_fetch writes metadata.json that execute_process can read."""

    def test_fetch_then_process_e2e_local_docx(self, tmp_path: Path) -> None:
        """End-to-end: fetch a local DOCX then process it to markdown."""
        import os

        from docline.app import execute_process
        from docline.app_models import ProcessRequest
        from docline.elt.execute import execute_elt_fetch

        # Set up workspace
        elt_dir = tmp_path / ".elt"
        elt_dir.mkdir()
        (elt_dir / "SampleDocument.docx").write_bytes(_make_minimal_docx())

        config_dir = elt_dir / "config"
        config_dir.mkdir()
        (config_dir / "docs.sources.yaml").write_text(
            (
                "sources:\n"
                "  - id: sample-docx\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "**/*.docx"\n'
            ),
            encoding="utf-8",
        )

        try:
            os.chdir(tmp_path)
            # Phase 1: fetch
            jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)
            assert len(jobs) == 1
            assert jobs[0].complete is True

            # Phase 2: process
            result = execute_process(
                ProcessRequest(staging_dir=".elt/staging", output_dir=".elt/output")
            )
        finally:
            os.chdir(Path(__file__).parents[2])

        assert result.success is True
        output_dir = tmp_path / ".elt" / "output"
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "Hello World from DOCX" in content
