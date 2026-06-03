"""Tests for the POSIX path normalization helper (F2.T1 / 010.007-T)."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from docline.paths import posixify_path


class TestPosixifyPathStrings:
    """String input cases covering Windows, POSIX, mixed, drive, UNC, trailing-slash."""

    @pytest.mark.parametrize(
        ("input_path", "expected"),
        [
            # POSIX inputs pass through unchanged.
            ("docs/design-docs/file.md", "docs/design-docs/file.md"),
            ("file.md", "file.md"),
            ("a/b/c", "a/b/c"),
            # Relative Windows-style backslash inputs.
            ("docs\\design-docs\\file.md", "docs/design-docs/file.md"),
            ("a\\b\\c", "a/b/c"),
            # Mixed separators.
            ("docs/design-docs\\file.md", "docs/design-docs/file.md"),
            ("a\\b/c", "a/b/c"),
            # Drive-letter absolute Windows path.
            ("C:\\Users\\agent\\file.md", "C:/Users/agent/file.md"),
            ("D:\\projects\\docline\\README.md", "D:/projects/docline/README.md"),
            # Drive-letter with mixed separators.
            ("C:\\Users/agent\\file.md", "C:/Users/agent/file.md"),
            # UNC paths (network share).
            ("\\\\server\\share\\file.md", "//server/share/file.md"),
            ("\\\\server\\share\\sub\\file.md", "//server/share/sub/file.md"),
            # Trailing separators preserved as forward slashes.
            ("docs/design-docs/", "docs/design-docs/"),
            ("docs\\design-docs\\", "docs/design-docs/"),
            # Single segment + trailing separator.
            ("docs/", "docs/"),
            ("docs\\", "docs/"),
            # Absolute POSIX path.
            ("/usr/local/bin", "/usr/local/bin"),
            ("/", "/"),
        ],
    )
    def test_string_inputs_normalize_to_posix(self, input_path: str, expected: str) -> None:
        """All string forms collapse to forward-slash POSIX representation."""
        assert posixify_path(input_path) == expected


class TestPosixifyPathPathObjects:
    """``os.PathLike`` inputs (PurePath flavors) round-trip to POSIX strings."""

    def test_pure_posix_path_passes_through(self) -> None:
        """A ``PurePosixPath`` is rendered with forward slashes."""
        assert posixify_path(PurePosixPath("docs/file.md")) == "docs/file.md"

    def test_pure_windows_path_with_drive_normalizes(self) -> None:
        """A ``PureWindowsPath`` with a drive letter normalizes to ``C:/...``."""
        assert posixify_path(PureWindowsPath("C:\\Users\\file.md")) == "C:/Users/file.md"

    def test_pure_windows_path_relative_normalizes(self) -> None:
        """Relative ``PureWindowsPath`` flips backslashes to forward slashes."""
        assert posixify_path(PureWindowsPath("docs\\design-docs\\file.md")) == (
            "docs/design-docs/file.md"
        )


class TestPosixifyPathEdgeCases:
    """Empty input and idempotency."""

    def test_empty_string_returns_empty(self) -> None:
        """Empty input yields empty output; the helper does not raise on empty paths."""
        assert posixify_path("") == ""

    @pytest.mark.parametrize(
        "input_path",
        [
            "docs/design-docs/file.md",
            "docs\\design-docs\\file.md",
            "C:\\Users\\agent\\file.md",
            "\\\\server\\share\\file.md",
        ],
    )
    def test_posixify_is_idempotent(self, input_path: str) -> None:
        """Applying ``posixify_path`` twice yields the same result as once."""
        once = posixify_path(input_path)
        twice = posixify_path(once)
        assert once == twice
