"""Typed exception hierarchy for OpenAPI / Swagger ingestion (050-F).

All OpenAPI ingestion failures derive from :class:`OpenApiError`, which in turn
derives from :class:`docline.schema.models.DoclineError`, so callers can catch
docline errors uniformly while still distinguishing spec-parse failures from
reference-resolution failures.
"""

from docline.schema.models import DoclineError


class OpenApiError(DoclineError):
    """Base exception for all OpenAPI ingestion errors."""


class OpenApiParseError(OpenApiError):
    """Raised when an OpenAPI specification cannot be read or parsed."""


class OpenApiRefError(OpenApiError):
    """Raised when a local ``$ref`` cannot be resolved or forms a cycle.

    External / split-file refs are *not* an error — they are intentionally left
    unresolved in v1. This exception covers only local (``#/``) refs that point
    at a missing target or participate in a circular ref chain.
    """


__all__ = ["OpenApiError", "OpenApiParseError", "OpenApiRefError"]
