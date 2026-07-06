"""Content-sniff detection for OpenAPI / Swagger specifications (050.001-T / T1).

A source is an API specification when its parsed root mapping carries an
``openapi`` key (OpenAPI 3.x) or a ``swagger`` key (Swagger 2.0). Extension
alone is insufficient: ``.json`` and ``.yaml`` are overloaded, and the process
pass deliberately skips config sidecars such as ``docfx.json`` and
``.openpublishing.publish.config.json``. Detection therefore inspects content,
never the file extension.

Detection is intentionally cheap and total: any parse failure or unexpected
shape yields a negative result rather than raising, so the sniff can be applied
broadly to staged files without a try/except at every call site.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# Marker returned for OpenAPI 3.x specifications (rendered by v1).
OPENAPI_3X = "openapi-3.x"
# Marker returned for Swagger 2.0 specifications (detected in v1; rendering
# deferred to a follow-up task).
SWAGGER_20 = "swagger-2.0"


def openapi_kind(text: str) -> str | None:
    """Sniff raw specification text and return its API-spec marker.

    The text is parsed with a YAML safe-loader, which accepts JSON as a strict
    subset of YAML, so a single parse handles both ``.json`` and ``.yaml``
    inputs. Only the root ``openapi`` / ``swagger`` keys are inspected.

    Args:
        text: Raw specification content (JSON or YAML).

    Returns:
        :data:`OPENAPI_3X` when the root declares ``openapi: 3.x``,
        :data:`SWAGGER_20` when the root declares ``swagger: 2.x``, or ``None``
        when the content is not a recognizable API specification (including
        unparseable, empty, or non-mapping input).
    """
    # Fast reject: a valid spec MUST declare a lowercase ``openapi`` (3.x) or
    # ``swagger`` (2.0) key, so the literal token is always present. Skipping the
    # (relatively expensive) YAML parse for the common case of unrelated config
    # JSON keeps the process-pass file scan cheap.
    if "openapi" not in text and "swagger" not in text:
        return None

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    version = data.get("openapi")
    if isinstance(version, str) and version.startswith("3."):
        return OPENAPI_3X

    swagger = data.get("swagger")
    if isinstance(swagger, str) and swagger.startswith("2."):
        return SWAGGER_20

    return None


def is_openapi_spec(text: str) -> bool:
    """Return ``True`` when *text* is an OpenAPI 3.x or Swagger 2.0 spec.

    Args:
        text: Raw specification content (JSON or YAML).

    Returns:
        ``True`` for any recognized API specification, ``False`` otherwise.
    """
    return openapi_kind(text) is not None


def detect_openapi_file(path: Path) -> bool:
    """Return ``True`` when the file at *path* content-sniffs as an API spec.

    Missing, unreadable, or non-UTF-8 files sniff negative rather than raising,
    keeping the detector safe to apply to arbitrary staged files.

    Args:
        path: Filesystem path to a candidate specification file.

    Returns:
        ``True`` when the file parses as an OpenAPI/Swagger specification.
    """
    return openapi_file_kind(path) is not None


def openapi_file_kind(path: Path) -> str | None:
    """Return the API-spec marker for the file at *path*, or ``None``.

    Like :func:`detect_openapi_file` but preserves the distinction between
    OpenAPI 3.x (:data:`OPENAPI_3X`) and Swagger 2.0 (:data:`SWAGGER_20`) so
    callers can gate on the version. Missing/unreadable files return ``None``.

    Args:
        path: Filesystem path to a candidate specification file.

    Returns:
        The spec marker, or ``None`` when the file is not a recognized spec.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return openapi_kind(text)


__all__ = [
    "OPENAPI_3X",
    "SWAGGER_20",
    "detect_openapi_file",
    "is_openapi_spec",
    "openapi_file_kind",
    "openapi_kind",
]
