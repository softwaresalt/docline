"""Tests for optional dependency guards."""

import pytest

from docline.dependencies import (
    DependencyUnavailableError,
    html_available,
    pdf_available,
    require_extra,
    transcript_available,
)
from docline.schema.models import DoclineError


def test_dependency_unavailable_error_is_docline_error() -> None:
    """DependencyUnavailableError is a subclass of DoclineError."""
    err = DependencyUnavailableError("missing pkg")
    assert isinstance(err, DoclineError)


def test_require_extra_raises_on_missing_package() -> None:
    """require_extra raises DependencyUnavailableError for a non-existent package."""
    with pytest.raises(DependencyUnavailableError):
        require_extra("__nonexistent_package__", "test-extra")


def test_require_extra_error_message_contains_package() -> None:
    """Error message from require_extra includes the package name."""
    with pytest.raises(DependencyUnavailableError, match="__nonexistent_package__"):
        require_extra("__nonexistent_package__", "test-extra")


def test_require_extra_error_message_contains_extra() -> None:
    """Error message from require_extra includes the extra name."""
    with pytest.raises(DependencyUnavailableError, match="test-extra"):
        require_extra("__nonexistent_package__", "test-extra")


def test_require_extra_does_not_raise_for_stdlib() -> None:
    """require_extra does not raise for packages that are available."""
    require_extra("json", "core")  # json is always available


def test_pdf_available_returns_bool() -> None:
    """pdf_available() returns a bool."""
    result = pdf_available()
    assert isinstance(result, bool)


def test_html_available_returns_bool() -> None:
    """html_available() returns a bool."""
    result = html_available()
    assert isinstance(result, bool)


def test_transcript_available_returns_true() -> None:
    """transcript_available() always returns True (stdlib-only path)."""
    assert transcript_available() is True
