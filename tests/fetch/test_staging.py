"""Tests for fetch staging job models and utilities."""

from datetime import UTC, datetime

from docline.fetch.models import SourceMetadata, StagingJob, StagingJobError
from docline.fetch.staging import (
    build_cache_path,
    create_staging_job,
    make_job_id,
    sanitize_source,
)
from docline.schema.models import DoclineError


def test_staging_job_error_is_docline_error() -> None:
    """StagingJobError is a subclass of DoclineError."""
    err = StagingJobError("staging failed")
    assert isinstance(err, DoclineError)


def test_source_metadata_valid_construction() -> None:
    """SourceMetadata accepts required fields."""
    meta = SourceMetadata(source="http://example.com", fetch_timestamp=datetime.now(UTC))
    assert meta.source == "http://example.com"
    assert meta.http_status is None
    assert meta.content_type is None


def test_source_metadata_with_optional_fields() -> None:
    """SourceMetadata accepts optional http_status and content_type."""
    meta = SourceMetadata(
        source="http://example.com",
        fetch_timestamp=datetime.now(UTC),
        http_status=200,
        content_type="text/html",
    )
    assert meta.http_status == 200
    assert meta.content_type == "text/html"


def test_staging_job_valid_construction() -> None:
    """StagingJob accepts required fields and defaults complete to False."""
    meta = SourceMetadata(source="http://example.com", fetch_timestamp=datetime.now(UTC))
    job = StagingJob(
        job_id="abcdef1234567890",
        metadata=meta,
        cache_path="/cache/ab/abcdef1234567890",
    )
    assert job.complete is False
    assert job.job_id == "abcdef1234567890"


def test_make_job_id_is_hex() -> None:
    """make_job_id returns a hex string."""
    job_id = make_job_id("http://example.com")
    assert all(c in "0123456789abcdef" for c in job_id)


def test_make_job_id_is_16_chars() -> None:
    """make_job_id returns first 16 hex chars."""
    job_id = make_job_id("http://example.com")
    assert len(job_id) == 16


def test_make_job_id_is_deterministic() -> None:
    """make_job_id returns the same value for the same input."""
    assert make_job_id("http://example.com") == make_job_id("http://example.com")


def test_make_job_id_differs_for_different_inputs() -> None:
    """make_job_id returns different values for different sources."""
    assert make_job_id("http://a.com") != make_job_id("http://b.com")


def test_build_cache_path_structure() -> None:
    """build_cache_path uses two-char prefix sharding."""
    path = build_cache_path(".cache/staging", "abcdef1234567890")
    assert path == ".cache/staging/ab/abcdef1234567890"


def test_build_cache_path_custom_base() -> None:
    """build_cache_path uses the provided base_dir."""
    path = build_cache_path("/data/cache", "ff0011223344556677")
    assert path.startswith("/data/cache/ff/")


def test_create_staging_job_returns_staging_job() -> None:
    """create_staging_job returns a valid StagingJob."""
    job = create_staging_job("http://example.com", ".cache/staging")
    assert isinstance(job, StagingJob)


def test_create_staging_job_stable_id() -> None:
    """create_staging_job produces a stable job_id for the same source."""
    job1 = create_staging_job("http://example.com", ".cache")
    job2 = create_staging_job("http://example.com", ".cache")
    assert job1.job_id == job2.job_id


def test_create_staging_job_cache_path() -> None:
    """create_staging_job cache_path uses two-char prefix."""
    job = create_staging_job("http://example.com", ".cache")
    job_id = job.job_id
    assert job.cache_path == f".cache/{job_id[:2]}/{job_id}"


def test_create_staging_job_with_http_status() -> None:
    """create_staging_job stores http_status in metadata."""
    job = create_staging_job("http://example.com", ".cache", http_status=200)
    assert job.metadata.http_status == 200


def test_create_staging_job_with_content_type() -> None:
    """create_staging_job stores content_type in metadata."""
    job = create_staging_job("http://example.com", ".cache", content_type="application/pdf")
    assert job.metadata.content_type == "application/pdf"


# --- sanitize_source tests ---


def test_sanitize_url_strips_token_query_param() -> None:
    """sanitize_source removes token= query parameter from URLs."""
    result = sanitize_source("https://example.com/doc?token=secret123&page=1")
    assert "token=" not in result
    assert "page=1" in result


def test_sanitize_url_strips_key_query_param() -> None:
    """sanitize_source removes key= query parameter from URLs."""
    result = sanitize_source("https://example.com/doc?key=abc&lang=en")
    assert "key=" not in result
    assert "lang=en" in result


def test_sanitize_url_strips_secret_query_param() -> None:
    """sanitize_source removes secret= query parameter from URLs."""
    result = sanitize_source("https://example.com/doc?secret=xyz")
    assert "secret=" not in result


def test_sanitize_url_strips_auth_query_param() -> None:
    """sanitize_source removes auth= query parameter from URLs."""
    result = sanitize_source("http://example.com/path?auth=tok&id=42")
    assert "auth=" not in result
    assert "id=42" in result


def test_sanitize_url_strips_sig_query_param() -> None:
    """sanitize_source removes sig= query parameter from URLs."""
    result = sanitize_source("https://cdn.example.com/file?sig=abc123")
    assert "sig=" not in result


def test_sanitize_url_strips_userinfo_from_netloc() -> None:
    """sanitize_source removes user:pass@ from URL netloc."""
    result = sanitize_source("https://user:pass@example.com/path")
    assert "user" not in result
    assert "pass" not in result
    assert "example.com" in result


def test_sanitize_url_no_credentials_unchanged() -> None:
    """sanitize_source leaves clean URLs without credentials unchanged."""
    url = "https://example.com/docs/api?page=2&lang=en"
    result = sanitize_source(url)
    assert result == url


def test_sanitize_windows_absolute_path() -> None:
    """sanitize_source replaces Windows absolute paths with sentinel."""
    result = sanitize_source(r"C:\Users\alice\documents\report.pdf")
    assert result == "<local-path-redacted>"


def test_sanitize_unix_absolute_path() -> None:
    """sanitize_source replaces Unix absolute paths with sentinel."""
    result = sanitize_source("/home/user/documents/report.pdf")
    assert result == "<local-path-redacted>"


def test_sanitize_relative_path_unchanged() -> None:
    """sanitize_source leaves relative file paths unchanged."""
    result = sanitize_source("docs/report.pdf")
    assert result == "docs/report.pdf"


def test_sanitize_plain_string_unchanged() -> None:
    """sanitize_source returns non-URL, non-path strings as-is."""
    result = sanitize_source("just-a-name")
    assert result == "just-a-name"
