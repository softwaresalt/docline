"""Red-first tests for content_sha256 hashing helper (F1.T4)."""

from docline.process.hashing import compute_content_sha256


def test_compute_content_sha256_returns_64_char_hex() -> None:
    """SHA-256 hex digest is 64 hex characters."""
    digest = compute_content_sha256("# Hello\n\nWorld\n")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_compute_content_sha256_is_deterministic() -> None:
    """Identical input produces identical digest."""
    body = "# Title\n\nSome body text.\n"
    assert compute_content_sha256(body) == compute_content_sha256(body)


def test_compute_content_sha256_differs_for_different_inputs() -> None:
    """Different inputs produce different digests."""
    a = compute_content_sha256("body a")
    b = compute_content_sha256("body b")
    assert a != b


def test_compute_content_sha256_uses_utf8_encoding() -> None:
    """Non-ASCII content hashes via UTF-8 byte sequence."""
    import hashlib

    body = "café"
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert compute_content_sha256(body) == expected


def test_compute_content_sha256_handles_empty_body() -> None:
    """Empty body hashes to the canonical empty-SHA256 digest."""
    digest = compute_content_sha256("")
    # Canonical SHA-256 of empty bytes.
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
