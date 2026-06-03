"""Red-first URL canonicalization tests (010-S F6.T3).

These tests pin the contract that F6.T4 (010.028-T) must satisfy when adding
``src/docline/fetch/url_canonical.py``:

* expose ``canonicalize_url(url: str) -> str`` plus a typed
  ``UrlCanonicalizationError(DoclineError)`` for unrecoverable input
* lowercase the scheme and host (the IETF case-insensitive components)
* drop the URL fragment (``#section``) because fragments are client-side
  navigation and never reach the server during fetch dedup
* strip default ports (``http://host:80`` → ``http://host``,
  ``https://host:443`` → ``https://host``)
* sort query parameters by key for stable comparison across mirrors
* drop common ad/analytics tracking params (``utm_*``, ``fbclid``, ``gclid``)
* normalize empty path to ``/``
* collapse duplicate path slashes and resolve ``.`` / ``..`` segments
* be idempotent — ``canonicalize_url(canonicalize_url(x))`` must equal
  ``canonicalize_url(x)`` for every input the function accepts
* raise on empty input and on URLs whose scheme is neither ``http`` nor
  ``https``; canonicalization is a fetch-time operation, not a generic
  URL rewriter

These assertions are expected to **fail today** because
``src/docline/fetch/url_canonical.py`` does not exist yet — the imports at
the top of this file will raise ``ImportError``. F6.T4 lands the module and
turns these red tests green.
"""

from __future__ import annotations

import pytest

from docline.fetch.url_canonical import (  # type: ignore[import-not-found]
    UrlCanonicalizationError,
    canonicalize_url,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy
# ---------------------------------------------------------------------------


def test_url_canonicalization_error_is_docline_error() -> None:
    """``UrlCanonicalizationError`` must subclass ``DoclineError``."""
    err = UrlCanonicalizationError("canonicalization failed")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: case folding for scheme and host
# ---------------------------------------------------------------------------


def test_canonicalize_lowercases_scheme() -> None:
    """Scheme must be lowercased per RFC 3986."""
    assert canonicalize_url("HTTP://example.com/path") == "http://example.com/path"
    assert canonicalize_url("HTTPS://example.com/path") == "https://example.com/path"


def test_canonicalize_lowercases_host() -> None:
    """Host component must be lowercased per RFC 3986."""
    assert canonicalize_url("https://EXAMPLE.com/path") == "https://example.com/path"
    assert canonicalize_url("https://Example.COM/Path") == "https://example.com/Path"


def test_canonicalize_preserves_case_in_path() -> None:
    """Path component is case-sensitive and must be preserved verbatim."""
    assert canonicalize_url("https://example.com/SomePath") == "https://example.com/SomePath"


# ---------------------------------------------------------------------------
# Behavioral: fragment removal
# ---------------------------------------------------------------------------


def test_canonicalize_drops_fragment() -> None:
    """Fragment identifiers must be stripped — they never reach the server."""
    assert canonicalize_url("https://example.com/page#section-2") == "https://example.com/page"
    assert canonicalize_url("https://example.com/#top") == "https://example.com/"


# ---------------------------------------------------------------------------
# Behavioral: default port removal
# ---------------------------------------------------------------------------


def test_canonicalize_drops_default_http_port() -> None:
    """``:80`` must be stripped from ``http`` URLs."""
    assert canonicalize_url("http://example.com:80/path") == "http://example.com/path"


def test_canonicalize_drops_default_https_port() -> None:
    """``:443`` must be stripped from ``https`` URLs."""
    assert canonicalize_url("https://example.com:443/path") == "https://example.com/path"


def test_canonicalize_preserves_non_default_port() -> None:
    """Non-default ports must be preserved verbatim."""
    assert canonicalize_url("https://example.com:8443/path") == "https://example.com:8443/path"


# ---------------------------------------------------------------------------
# Behavioral: query parameter handling
# ---------------------------------------------------------------------------


def test_canonicalize_sorts_query_parameters() -> None:
    """Query parameters must be sorted by key for stable comparison."""
    assert (
        canonicalize_url("https://example.com/?b=2&a=1&c=3") == "https://example.com/?a=1&b=2&c=3"
    )


def test_canonicalize_drops_utm_tracking_params() -> None:
    """``utm_*`` analytics parameters must be removed."""
    result = canonicalize_url(
        "https://example.com/page?utm_source=newsletter&utm_medium=email&id=42"
    )
    assert "utm_source" not in result
    assert "utm_medium" not in result
    assert "id=42" in result


def test_canonicalize_drops_fbclid_and_gclid() -> None:
    """``fbclid`` and ``gclid`` click-tracking params must be removed."""
    result = canonicalize_url("https://example.com/page?fbclid=abc&gclid=xyz&q=docs")
    assert "fbclid" not in result
    assert "gclid" not in result
    assert "q=docs" in result


def test_canonicalize_preserves_legitimate_query_params() -> None:
    """Non-tracking query params must round-trip unchanged."""
    result = canonicalize_url("https://example.com/search?q=python&page=2")
    assert "q=python" in result
    assert "page=2" in result


def test_canonicalize_drops_query_when_only_tracking_params() -> None:
    """When all query params are tracking, the ``?`` separator must go too."""
    result = canonicalize_url("https://example.com/page?utm_source=email&fbclid=x")
    assert result == "https://example.com/page"


# ---------------------------------------------------------------------------
# Behavioral: path normalization
# ---------------------------------------------------------------------------


def test_canonicalize_normalizes_empty_path_to_root() -> None:
    """Empty path must become ``/`` for consistent crawl dedup."""
    assert canonicalize_url("https://example.com") == "https://example.com/"


def test_canonicalize_collapses_duplicate_slashes() -> None:
    """Repeated path slashes must be collapsed."""
    assert canonicalize_url("https://example.com//a//b///c") == "https://example.com/a/b/c"


def test_canonicalize_resolves_dot_segments() -> None:
    """``.`` and ``..`` segments must be resolved per RFC 3986 §5.2.4."""
    assert canonicalize_url("https://example.com/a/./b/../c") == "https://example.com/a/c"


# ---------------------------------------------------------------------------
# Behavioral: idempotency
# ---------------------------------------------------------------------------


def test_canonicalize_is_idempotent() -> None:
    """Applying ``canonicalize_url`` twice must equal applying it once."""
    samples = [
        "HTTPS://Example.COM:443/A/./B/../C?b=2&a=1&utm_source=x#frag",
        "http://example.com",
        "https://example.com/page?q=docs",
        "https://example.com//a//b",
    ]
    for url in samples:
        once = canonicalize_url(url)
        twice = canonicalize_url(once)
        assert once == twice, f"non-idempotent for {url!r}: {once!r} -> {twice!r}"


# ---------------------------------------------------------------------------
# Behavioral: input validation
# ---------------------------------------------------------------------------


def test_canonicalize_rejects_empty_input() -> None:
    """Empty input must raise ``UrlCanonicalizationError``."""
    with pytest.raises(UrlCanonicalizationError):
        canonicalize_url("")


def test_canonicalize_rejects_non_http_scheme() -> None:
    """Non-``http``/``https`` schemes must raise — canonicalization is a fetch op."""
    with pytest.raises(UrlCanonicalizationError):
        canonicalize_url("ftp://example.com/path")
    with pytest.raises(UrlCanonicalizationError):
        canonicalize_url("file:///etc/passwd")


def test_canonicalize_rejects_missing_host() -> None:
    """URLs without a host must raise."""
    with pytest.raises(UrlCanonicalizationError):
        canonicalize_url("http:///path-only")
