"""Reader safety limits — reject oversized, malformed, or untrusted inputs."""

from dataclasses import dataclass
from pathlib import Path

from docline.schema.models import DoclineError

# Maximum file size accepted by any reader (default: 50 MB).
DEFAULT_MAX_BYTES: int = 50 * 1024 * 1024

# MIME types that are only accepted from trusted-local sources in v1.
TRUSTED_LOCAL_ONLY_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


class ReaderLimitExceededError(DoclineError):
    """Raised when a document input exceeds a configured reader limit."""


class UntrustedSourceError(DoclineError):
    """Raised when a restricted document type is submitted from an untrusted source."""


@dataclass(frozen=True)
class ReaderLimits:
    """Configuration for document reader safety checks.

    Attributes:
        max_bytes: Maximum file size in bytes.
        trusted_local_only: When ``True``, restrict PDF and DOCX parsing to
            files whose origin has been verified as a trusted local path.
        allowed_mime_types: Set of MIME type strings to accept.  An empty
            set means all types are accepted (subject to other limits).
    """

    max_bytes: int = DEFAULT_MAX_BYTES
    trusted_local_only: bool = True
    allowed_mime_types: frozenset[str] = frozenset()


def validate_document_input(
    path: Path,
    limits: ReaderLimits,
    *,
    mime_hint: str | None = None,
    trusted: bool = False,
) -> None:
    """Validate a document path against the configured reader safety limits.

    Checks applied in order:

    1. File must exist and be a regular file.
    2. File size must not exceed ``limits.max_bytes``.
    3. If ``mime_hint`` is provided and ``limits.allowed_mime_types`` is
       non-empty, the MIME type must be in the allowed set.
    4. If the MIME type is in :data:`TRUSTED_LOCAL_ONLY_TYPES` and
       ``limits.trusted_local_only`` is ``True``, ``trusted`` must be
       ``True``.

    Args:
        path: Filesystem path to the document to validate.
        limits: Reader limit configuration.
        mime_hint: Optional MIME type hint (e.g. from a Content-Type header).
        trusted: Whether the source has been verified as trusted-local.

    Raises:
        ReaderLimitExceededError: If the file exceeds size limits or the
            MIME type is not in the allowed set.
        UntrustedSourceError: If a restricted document type is submitted
            without trusted-local verification.
        FileNotFoundError: If ``path`` does not exist or is not a regular file.
    """
    raise NotImplementedError("stub: limits.validate_document_input not yet implemented")


__all__ = [
    "DEFAULT_MAX_BYTES",
    "ReaderLimitExceededError",
    "ReaderLimits",
    "TRUSTED_LOCAL_ONLY_TYPES",
    "UntrustedSourceError",
    "validate_document_input",
]
