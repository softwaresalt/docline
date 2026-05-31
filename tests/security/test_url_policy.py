"""Test harness for 003.001-T — Reject unsafe crawl URLs.

Acceptance criteria:
- Reject non-http/https schemes (ftp, file, data).
- Reject loopback addresses (127.0.0.1, ::1, localhost).
- Reject RFC 1918 private addresses (10.x, 192.168.x, 172.16-31.x).
- Reject link-local / cloud metadata service addresses (169.254.169.254).
- Accept valid public https URLs unchanged.
- Reject redirect chains that exceed MAX_REDIRECTS.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests call stubs expecting typed exceptions or return values (FAIL in red
phase because stubs raise NotImplementedError).
"""

import pytest

from docline.fetch.url_policy import (
    MAX_REDIRECTS,
    CrawlUrlRejectedError,
    assert_redirect_count,
    is_private_host,
    validate_crawl_url,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy (PASS in red phase — scaffold correct)
# ---------------------------------------------------------------------------


def test_crawl_url_rejected_error_is_docline_error() -> None:
    """CrawlUrlRejectedError is a subclass of DoclineError."""
    err = CrawlUrlRejectedError("rejected")
    assert isinstance(err, DoclineError)


def test_max_redirects_is_positive_int() -> None:
    """MAX_REDIRECTS is a positive integer constant."""
    assert isinstance(MAX_REDIRECTS, int)
    assert MAX_REDIRECTS > 0


# ---------------------------------------------------------------------------
# Behavioral: validate_crawl_url — scheme enforcement (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_validate_crawl_url_rejects_ftp_scheme() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for ftp:// URLs."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("ftp://example.com/file.txt")


def test_validate_crawl_url_rejects_file_scheme() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for file:// URLs."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("file:///etc/passwd")


def test_validate_crawl_url_rejects_data_scheme() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for data: URLs."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("data:text/html,<h1>x</h1>")


def test_validate_crawl_url_accepts_https_returns_url() -> None:
    """validate_crawl_url returns the URL unchanged for valid https."""
    result = validate_crawl_url("https://example.com/page")
    assert result == "https://example.com/page"


def test_validate_crawl_url_accepts_http_returns_url() -> None:
    """validate_crawl_url returns the URL unchanged for valid http."""
    result = validate_crawl_url("http://example.com/page")
    assert result == "http://example.com/page"


# ---------------------------------------------------------------------------
# Behavioral: SSRF / private address rejection (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_validate_crawl_url_rejects_localhost() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for localhost."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://localhost/admin")


def test_validate_crawl_url_rejects_loopback_ipv4() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for 127.0.0.1."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://127.0.0.1:8080/internal")


def test_validate_crawl_url_rejects_rfc1918_10_block() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for 10.x.x.x."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://10.0.0.1/secret")


def test_validate_crawl_url_rejects_rfc1918_192168_block() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for 192.168.x.x."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://192.168.1.1/admin")


def test_validate_crawl_url_rejects_rfc1918_172_block() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for 172.16-31.x.x."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://172.16.0.1/internal")


def test_validate_crawl_url_rejects_metadata_service() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for 169.254.169.254."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://169.254.169.254/latest/meta-data/")


def test_validate_crawl_url_rejects_ipv6_loopback() -> None:
    """validate_crawl_url raises CrawlUrlRejectedError for IPv6 ::1."""
    with pytest.raises(CrawlUrlRejectedError):
        validate_crawl_url("http://[::1]/internal")


# ---------------------------------------------------------------------------
# Behavioral: is_private_host (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_is_private_host_returns_true_for_loopback() -> None:
    """is_private_host returns True for 127.0.0.1."""
    assert is_private_host("127.0.0.1") is True


def test_is_private_host_returns_true_for_rfc1918() -> None:
    """is_private_host returns True for 10.0.0.1."""
    assert is_private_host("10.0.0.1") is True


def test_is_private_host_returns_true_for_metadata_service() -> None:
    """is_private_host returns True for 169.254.169.254."""
    assert is_private_host("169.254.169.254") is True


def test_is_private_host_returns_false_for_public_ip() -> None:
    """is_private_host returns False for a public IP."""
    assert is_private_host("93.184.216.34") is False


def test_is_private_host_returns_true_for_localhost_name() -> None:
    """is_private_host returns True for the string 'localhost'."""
    assert is_private_host("localhost") is True


# ---------------------------------------------------------------------------
# Behavioral: assert_redirect_count (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_assert_redirect_count_does_not_raise_at_zero() -> None:
    """assert_redirect_count completes without error when count is 0."""
    assert_redirect_count(0)  # raises NotImplementedError in red phase


def test_assert_redirect_count_does_not_raise_one_below_limit() -> None:
    """assert_redirect_count completes without error one below the limit."""
    assert_redirect_count(MAX_REDIRECTS - 1)


def test_assert_redirect_count_raises_above_limit() -> None:
    """assert_redirect_count raises CrawlUrlRejectedError above the limit."""
    with pytest.raises(CrawlUrlRejectedError):
        assert_redirect_count(MAX_REDIRECTS + 1)
