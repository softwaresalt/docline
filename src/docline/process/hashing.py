"""Content hashing helpers for document assembly."""

import hashlib


def compute_content_sha256(body: str) -> str:
    """Compute the SHA-256 hex digest of a Markdown body string.

    The body is encoded as UTF-8 and hashed with SHA-256. The result is a
    64-character lowercase hex digest suitable for storage in the
    ``content_sha256`` frontmatter field defined by the v1 contract.

    Args:
        body: Markdown body text whose canonical bytes should be hashed.

    Returns:
        Lowercase hex digest (length 64).
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


__all__ = ["compute_content_sha256"]
