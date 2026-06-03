"""URL canonicalization stub — staged scaffolding for F6.T4 (010.028-T).

This module exists so the red-first contract tests in
``tests/fetch/test_url_canonical.py`` collect cleanly. ``canonicalize_url``
raises :class:`NotImplementedError` until F6.T4 lands the real
canonicalization rules (case folding, default-port stripping, fragment
removal, query sort, tracking-param drop, path normalization).
"""

from docline.schema.models import DoclineError


class UrlCanonicalizationError(DoclineError):
    """Raised when a URL cannot be canonicalized."""


def canonicalize_url(url: str) -> str:  # noqa: ARG001
    """Stub — F6.T4 implements the canonicalization rules pinned by tests."""
    raise NotImplementedError(
        "canonicalize_url is implemented by F6.T4 (010.028-T); "
        "this stub exists so the red-first contract tests collect cleanly."
    )


__all__ = ["UrlCanonicalizationError", "canonicalize_url"]
