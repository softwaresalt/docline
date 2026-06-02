"""Regression tests for the GitHub reader — glob pattern matching.

Covers:
- ``**/*.md`` must match top-level files (e.g. README.md) as well as nested ones.
- Basename-only patterns (``*.md``) still match nested files via basename fallback.
- Non-matching extensions are correctly rejected.
"""

import json
from unittest.mock import patch

import pytest

from docline.readers.github import GitHubFetchError, _path_matches_pattern, fetch_github_files

# ---------------------------------------------------------------------------
# Unit tests: _path_matches_pattern
# ---------------------------------------------------------------------------


def test_double_glob_matches_top_level_md() -> None:
    """**/*.md must match a top-level file like README.md."""
    assert _path_matches_pattern("README.md", "**/*.md") is True


def test_double_glob_matches_nested_md() -> None:
    """**/*.md must match a file in a subdirectory."""
    assert _path_matches_pattern("docs/guide.md", "**/*.md") is True


def test_double_glob_matches_deeply_nested_md() -> None:
    """**/*.md must match files in any depth of subdirectory."""
    assert _path_matches_pattern("a/b/c/deep.md", "**/*.md") is True


def test_double_glob_rejects_non_matching_extension() -> None:
    """**/*.md must NOT match README.txt."""
    assert _path_matches_pattern("README.txt", "**/*.md") is False


def test_double_glob_rejects_nested_non_matching_extension() -> None:
    """**/*.md must NOT match docs/file.txt."""
    assert _path_matches_pattern("docs/file.txt", "**/*.md") is False


def test_basename_only_pattern_matches_nested_file() -> None:
    """*.md basename pattern should match a nested file via basename fallback."""
    assert _path_matches_pattern("src/README.md", "*.md") is True


def test_exact_filename_pattern_matches_direct() -> None:
    """An exact filename pattern matches the file directly."""
    assert _path_matches_pattern("README.md", "README.md") is True


def test_exact_filename_pattern_matches_nested_via_basename() -> None:
    """An exact filename pattern matches a nested file via basename fallback."""
    assert _path_matches_pattern("docs/README.md", "README.md") is True


def test_double_glob_matches_multiple_extensions() -> None:
    """**/*.txt matches top-level .txt files too."""
    assert _path_matches_pattern("CHANGELOG.txt", "**/*.txt") is True


# ---------------------------------------------------------------------------
# Helpers for integration tests that need mocked HTTP
# ---------------------------------------------------------------------------


class _MockHTTPResponse:
    """Minimal mock for a urllib response used as a context manager."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        """Return the response body bytes."""
        return self._content

    def __enter__(self) -> "_MockHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        pass


# ---------------------------------------------------------------------------
# Integration tests: fetch_github_files uses _path_matches_pattern
# ---------------------------------------------------------------------------


def test_fetch_github_files_includes_top_level_md_with_double_glob() -> None:
    """fetch_github_files returns top-level .md files when pattern is **/*.md."""
    trees_payload = {
        "tree": [
            {"path": "README.md", "type": "blob"},
            {"path": "CHANGELOG.md", "type": "blob"},
            {"path": "src/module.py", "type": "blob"},
        ]
    }

    def _mock_http_get(url: str) -> str:
        return json.dumps(trees_payload)

    def _mock_urlopen(req: object, timeout: object = None) -> _MockHTTPResponse:
        return _MockHTTPResponse(b"# Document\n\nContent.")

    with (
        patch("docline.readers.github._http_get", side_effect=_mock_http_get),
        patch("docline.readers.github.request.urlopen", side_effect=_mock_urlopen),
    ):
        results = fetch_github_files("https://github.com/org/repo", "main", ["**/*.md"])

    paths = [r[0] for r in results]
    assert "README.md" in paths
    assert "CHANGELOG.md" in paths
    assert "src/module.py" not in paths


def test_fetch_github_files_excludes_non_md_top_level() -> None:
    """fetch_github_files does not include .py files when pattern is **/*.md."""
    trees_payload = {
        "tree": [
            {"path": "setup.py", "type": "blob"},
            {"path": "README.md", "type": "blob"},
        ]
    }

    def _mock_http_get(url: str) -> str:
        return json.dumps(trees_payload)

    def _mock_urlopen(req: object, timeout: object = None) -> _MockHTTPResponse:
        return _MockHTTPResponse(b"content")

    with (
        patch("docline.readers.github._http_get", side_effect=_mock_http_get),
        patch("docline.readers.github.request.urlopen", side_effect=_mock_urlopen),
    ):
        results = fetch_github_files("https://github.com/org/repo", "main", ["**/*.md"])

    paths = [r[0] for r in results]
    assert "README.md" in paths
    assert "setup.py" not in paths


def test_fetch_github_files_raises_for_non_github_url() -> None:
    """fetch_github_files raises GitHubFetchError for a non-GitHub URL."""
    with pytest.raises(GitHubFetchError):
        fetch_github_files("https://gitlab.com/org/repo", "main", ["**/*.md"])


def test_fetch_github_files_wraps_tree_json_decode_errors() -> None:
    """fetch_github_files adapts tree JSON decode failures to GitHubFetchError."""
    with patch("docline.readers.github._http_get", return_value="{not json"):
        with pytest.raises(GitHubFetchError, match="Invalid JSON"):
            fetch_github_files("https://github.com/org/repo", "main", ["**/*.md"])


def test_fetch_github_files_wraps_unexpected_tree_payload_shape() -> None:
    """fetch_github_files rejects malformed Trees API payloads with GitHubFetchError."""
    with patch(
        "docline.readers.github._http_get",
        return_value=json.dumps({"tree": {"path": "x"}}),
    ):
        with pytest.raises(GitHubFetchError, match="Unexpected GitHub Trees API payload"):
            fetch_github_files("https://github.com/org/repo", "main", ["**/*.md"])
