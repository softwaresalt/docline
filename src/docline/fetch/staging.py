"""Utilities for building and managing fetch-stage jobs."""

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from docline.fetch.models import SourceMetadata, StagingJob

_CREDENTIAL_PARAM_PREFIXES = ("token", "key", "secret", "auth", "sig", "signature")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:", re.ASCII)


def make_job_id(source: str) -> str:
    """Compute a deterministic hex job ID from a source string.

    Uses the first 16 characters of the SHA-256 hex digest of the source.

    Args:
        source: The source URL or file path.

    Returns:
        A 16-character lowercase hex string.
    """
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def build_cache_path(base_dir: str, job_id: str) -> str:
    """Build a sharded cache path for a staging job.

    The first two characters of ``job_id`` are used as a subdirectory prefix
    to avoid very large flat directories.

    Args:
        base_dir: Root cache directory.
        job_id: Deterministic job identifier.

    Returns:
        A path string of the form ``{base_dir}/{job_id[:2]}/{job_id}``.
    """
    return f"{base_dir}/{job_id[:2]}/{job_id}"


def sanitize_source(source: str) -> str:
    """Remove credentials and sensitive data from a source string before staging.

    Rules applied in order:

    1. **URL** (starts with ``http://`` or ``https://``): strip ``userinfo``
       from the netloc and remove query parameters whose names match credential
       prefixes (``token``, ``key``, ``secret``, ``auth``, ``sig``,
       ``signature``, ``X-Amz-Signature``, ``X-Goog-Signature``).
       Matching is case-insensitive prefix comparison.
    2. **Absolute file path**: replace with ``"<local-path-redacted>"`` when
       the string starts with a Windows drive letter + colon (e.g. ``C:``) or
       a Unix root slash (``/``).
    3. **Everything else**: return as-is.

    Args:
        source: The raw source string to sanitise.

    Returns:
        A sanitised copy of the source string with credentials removed.
    """
    if source.startswith(("http://", "https://")):
        return _sanitize_url(source)
    if source.startswith("/") or _WINDOWS_DRIVE_RE.match(source):
        return "<local-path-redacted>"
    return source


def _sanitize_url(source: str) -> str:
    """Strip credentials from a URL string.

    Args:
        source: A URL string starting with ``http://`` or ``https://``.

    Returns:
        The URL with userinfo and credential query parameters removed.
    """
    parsed = urlparse(source)
    # Strip userinfo (user:pass@) from netloc
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    # Filter credential query params (case-insensitive prefix match)
    clean_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_credential_param(k)
    ]
    clean_query = urlencode(clean_params)

    sanitized = urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, clean_query, parsed.fragment)
    )
    return sanitized


def _is_credential_param(name: str) -> bool:
    """Return True if a query parameter name looks like a credential.

    Args:
        name: Query parameter name.

    Returns:
        ``True`` if the name matches a known credential prefix.
    """
    lower = name.lower()
    return any(lower.startswith(prefix) for prefix in _CREDENTIAL_PARAM_PREFIXES)


def create_staging_job(
    source: str,
    base_dir: str,
    http_status: int | None = None,
    content_type: str | None = None,
) -> StagingJob:
    """Create a new StagingJob for the given source.

    Args:
        source: The source URL or file path to stage.
        base_dir: Root directory for the cache layout.
        http_status: Optional HTTP status code from the fetch response.
        content_type: Optional MIME type from the fetch response.

    Returns:
        A :class:`~docline.fetch.models.StagingJob` with a deterministic
        ``job_id`` and a sharded ``cache_path``.
    """
    job_id = make_job_id(source)
    cache_path = build_cache_path(base_dir, job_id)
    metadata = SourceMetadata(
        source=sanitize_source(source),
        fetch_timestamp=datetime.now(UTC),
        http_status=http_status,
        content_type=content_type,
    )
    return StagingJob(job_id=job_id, metadata=metadata, cache_path=cache_path)
