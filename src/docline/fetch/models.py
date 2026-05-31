"""Data models for fetch-stage job tracking."""

from datetime import datetime

from pydantic import BaseModel

from docline.schema.models import DoclineError


class StagingJobError(DoclineError):
    """Raised when a staging operation fails."""


class SourceMetadata(BaseModel):
    """Metadata captured during a document fetch operation.

    Attributes:
        source: The sanitized source URL or file path persisted with the staging job.
        fetch_timestamp: When the fetch was initiated.
        http_status: HTTP response status code, if applicable.
        content_type: MIME type of the fetched content, if available.
    """

    source: str
    fetch_timestamp: datetime
    http_status: int | None = None
    content_type: str | None = None


class StagingJob(BaseModel):
    """Record tracking a single staged document fetch.

    Attributes:
        job_id: Deterministic hex identifier derived from the source string.
        metadata: Capture metadata from the fetch operation.
        cache_path: Filesystem path to the staged content.
        complete: Whether the staging job has completed successfully.
    """

    job_id: str
    metadata: SourceMetadata
    cache_path: str
    complete: bool = False
