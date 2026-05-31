"""Guarded import utilities for optional docline dependencies."""

import importlib

from docline.schema.models import DoclineError


class DependencyUnavailableError(DoclineError):
    """Raised when an optional extra package is not installed."""


def require_extra(package: str, extra: str) -> None:
    """Assert that an optional package is importable, raising if not.

    Args:
        package: The Python import name of the required package.
        extra: The docline extras name that installs the package
            (used in the error message).

    Raises:
        DependencyUnavailableError: If ``package`` cannot be imported.
    """
    try:
        importlib.import_module(package)
    except ImportError as err:
        raise DependencyUnavailableError(
            f"Install docline[{extra}] to use this feature (missing: {package})"
        ) from err


def pdf_available() -> bool:
    """Check whether the PDF processing dependency (docling) is available.

    Returns:
        ``True`` if ``docling`` can be imported, ``False`` otherwise.
    """
    try:
        importlib.import_module("docling")
        return True
    except ImportError:
        return False


def html_available() -> bool:
    """Check whether the HTML processing dependency (trafilatura) is available.

    Returns:
        ``True`` if ``trafilatura`` can be imported, ``False`` otherwise.
    """
    try:
        importlib.import_module("trafilatura")
        return True
    except ImportError:
        return False


def transcript_available() -> bool:
    """Check whether transcript processing is available.

    Transcript processing uses only stdlib modules and is always available.

    Returns:
        Always ``True``.
    """
    return True
