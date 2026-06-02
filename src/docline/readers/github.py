"""GitHub repository file fetcher using the public REST API.

Fetches files from a GitHub repository using the Trees API for directory
listing and raw.githubusercontent.com for content.  Uses only the Python
standard library (``urllib``) and imposes no new runtime dependencies.

Rate limits: unauthenticated requests are capped at 60 requests/hour.
For small sets of markdown files this is acceptable.
"""

import fnmatch
import json
import re
from urllib import error, request
from urllib.parse import urlparse

from docline.schema.models import DoclineError

_GITHUB_HOST_RE = re.compile(r"^(?:www\.)?github\.com$", re.IGNORECASE)
_TREES_URL = "https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
_RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
_USER_AGENT = "docline-fetcher/1.0"
_FETCH_TIMEOUT_SECONDS = 30


class GitHubFetchError(DoclineError):
    """Raised when a GitHub API or raw-content fetch fails."""


def _parse_github_url(repo_url: str) -> tuple[str, str]:
    """Extract the owner and repository name from a GitHub repository URL.

    Supports ``https://github.com/owner/repo`` and
    ``https://github.com/owner/repo.git`` forms.

    Args:
        repo_url: GitHub repository URL.

    Returns:
        A ``(owner, repo)`` tuple with the ``.git`` suffix stripped.

    Raises:
        GitHubFetchError: If the URL is not a recognised GitHub URL.
    """
    parsed = urlparse(repo_url)
    if not _GITHUB_HOST_RE.match(parsed.netloc):
        raise GitHubFetchError(
            f"Not a GitHub URL: {repo_url!r}; expected https://github.com/owner/repo[.git]"
        )
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise GitHubFetchError(f"Cannot extract owner/repo from GitHub URL: {repo_url!r}")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo


def _http_get(url: str) -> str:
    """Perform a simple HTTP GET and return the response body as text.

    Args:
        url: URL to fetch.

    Returns:
        Decoded response body.

    Raises:
        GitHubFetchError: If the request fails or returns a non-2xx status.
    """
    req = request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as err:
        raise GitHubFetchError(f"HTTP {err.code} fetching {url}: {err.reason}") from err
    except OSError as err:
        raise GitHubFetchError(f"Network error fetching {url}: {err}") from err


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Return True if ``path`` matches ``pattern`` with ``**`` root compatibility.

    Checks are applied in order:

    1. Direct ``fnmatch`` of the full path against the pattern.
    2. ``fnmatch`` of the path basename against the full pattern (handles
       patterns like ``*.md`` for files in any directory).
    3. When the pattern starts with ``**/``, strip that prefix and test the
       basename against the remainder (e.g. ``**/*.md`` must also match
       top-level ``README.md``).

    Args:
        path: Workspace-relative file path (forward-slash separated).
        pattern: Glob pattern to test against.

    Returns:
        ``True`` if the path should be included.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    basename = path.split("/")[-1]
    if fnmatch.fnmatch(basename, pattern):
        return True
    # Compatibility: **/<suffix> must also match top-level basenames where
    # the standard fnmatch does not treat ** as crossing directory boundaries.
    if pattern.startswith("**/"):
        tail = pattern[3:]
        if fnmatch.fnmatch(basename, tail):
            return True
    return False


def fetch_github_files(
    repo_url: str,
    branch: str,
    include_patterns: list[str],
) -> list[tuple[str, str]]:
    """Fetch files from a GitHub repository matching the given include patterns.

    Uses the GitHub Trees API (unauthenticated, recursive) to list all files,
    filters by ``include_patterns`` using :func:`_path_matches_pattern`, then
    fetches matching file content from ``raw.githubusercontent.com``.

    Args:
        repo_url: GitHub repository URL (``https://github.com/owner/repo[.git]``).
        branch: Branch name to read from.
        include_patterns: Glob patterns applied to workspace-relative file paths.
            Both the full relative path and the filename basename are tested;
            a match on either includes the file.  The pattern ``**/*.md`` also
            matches top-level markdown files via the ``**/`` compatibility rule.

    Returns:
        A list of ``(relative_path, text_content)`` tuples for each matched file.

    Raises:
        GitHubFetchError: If the API request or any file fetch fails.
    """
    owner, repo = _parse_github_url(repo_url)

    trees_url = _TREES_URL.format(owner=owner, repo=repo, branch=branch)
    raw_response = _http_get(trees_url)
    all_paths = _extract_tree_paths(raw_response, trees_url)

    matched_paths = [
        p
        for p in all_paths
        if any(_path_matches_pattern(p, pattern) for pattern in include_patterns)
    ]

    results: list[tuple[str, str]] = []
    for rel_path in matched_paths:
        raw_url = _RAW_URL.format(owner=owner, repo=repo, branch=branch, path=rel_path)
        req = request.Request(raw_url, headers={"User-Agent": _USER_AGENT})
        try:
            with request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as err:
            raise GitHubFetchError(f"HTTP {err.code} fetching {raw_url}: {err.reason}") from err
        except OSError as err:
            raise GitHubFetchError(f"Network error fetching {raw_url}: {err}") from err
        results.append((rel_path, content))

    return results


def _extract_tree_paths(raw_response: str, trees_url: str) -> list[str]:
    """Parse and validate file paths from a GitHub Trees API response."""
    try:
        trees_data = json.loads(raw_response)
    except json.JSONDecodeError as err:
        raise GitHubFetchError(f"Invalid JSON from GitHub Trees API {trees_url}") from err

    if not isinstance(trees_data, dict):
        raise GitHubFetchError(
            f"Unexpected GitHub Trees API payload from {trees_url}: expected an object"
        )

    tree_items = trees_data.get("tree")
    if not isinstance(tree_items, list):
        raise GitHubFetchError(
            f"Unexpected GitHub Trees API payload from {trees_url}: expected 'tree' list"
        )

    all_paths: list[str] = []
    for item in tree_items:
        if not isinstance(item, dict):
            raise GitHubFetchError(
                "Unexpected GitHub Trees API payload from "
                f"{trees_url}: tree entries must be objects"
            )
        if item.get("type") != "blob":
            continue
        path = item.get("path")
        if not isinstance(path, str):
            raise GitHubFetchError(
                "Unexpected GitHub Trees API payload from "
                f"{trees_url}: blob entries need string paths"
            )
        all_paths.append(path)
    return all_paths


__all__ = [
    "GitHubFetchError",
    "_path_matches_pattern",
    "fetch_github_files",
]
