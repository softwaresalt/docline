"""Utilities for building and managing fetch-stage jobs."""

import hashlib
from datetime import UTC, datetime

from docline.fetch.models import SourceMetadata, StagingJob


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
        source=source,
        fetch_timestamp=datetime.now(UTC),
        http_status=http_status,
        content_type=content_type,
    )
    return StagingJob(job_id=job_id, metadata=metadata, cache_path=cache_path)
