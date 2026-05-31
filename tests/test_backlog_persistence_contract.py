"""Tests verifying the backlog artifact persistence contract.

These tests prove that:

* Durable backlog artifacts (queue markdown, shipment markdown, archive markdown,
  config files) are not excluded by .gitignore patterns.
* Volatile runtime artifacts (database, WAL, event queue, logs) remain excluded.

The contract is data-driven: add a path to ``_DURABLE_PATHS`` or
``_VOLATILE_PATHS`` to extend coverage without writing a new test function.

The tests use ``git check-ignore --no-index`` so they evaluate raw .gitignore
pattern matching, independent of which files happen to be force-tracked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


class _GitCheckIgnoreError(RuntimeError):
    """Raised when ``git check-ignore`` fails unexpectedly."""


# Paths that MUST be Git-trackable (not matched by any .gitignore rule).
# Archive artifacts belong here: completed/archived backlog items are part
# of backlog durability and must remain accessible in version history.
_DURABLE_PATHS: list[str] = [
    # Active queue artifacts
    ".backlogit/queue/001-F.md",
    ".backlogit/queue/001-S.md",
    ".backlogit/queue/001.001-T.md",
    # Durable continuity artifacts
    ".backlogit/checkpoints/ship-001-S.json",
    # Top-level durable files
    ".backlogit/stash.jsonl",
    ".backlogit/config.yaml",
    ".backlogit/registry.yaml",
    # Archive artifacts — completed items remain trackable for history
    ".backlogit/archive/001-F.md",
    ".backlogit/archive/stash.jsonl",
]

# Paths that MUST be excluded by .gitignore (runtime-only, never committed).
_VOLATILE_PATHS: list[str] = [
    # SQLite database and journal files
    ".backlogit/backlogit.db",
    ".backlogit/backlogit.db-journal",
    ".backlogit/backlogit.db-wal",
    ".backlogit/backlogit.db-shm",
    # Telemetry output
    ".backlogit/telemetry.jsonl",
    ".backlogit/telemetry/session-001.jsonl",
    # Hook event queue written at runtime
    ".backlogit/hooks_queue.jsonl",
    # Session log files
    ".backlogit/logs/session.log",
]


def _git_ignores(relative_path: str) -> bool:
    """Return True if git's ignore rules would exclude the given path.

    Uses ``--no-index`` so the check is purely pattern-based and is not
    affected by whether the file is already tracked.

    Args:
        relative_path: Path relative to the repository root.

    Returns:
        True if the path matches an ignore rule, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", relative_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        message = (
            f"git check-ignore failed for {relative_path!r}: "
            "git executable is not available on PATH"
        )
        raise _GitCheckIgnoreError(message) from exc

    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False

    details = [
        f"git check-ignore failed for {relative_path!r}",
        f"return code={result.returncode}",
    ]
    if result.stderr:
        details.append(f"stderr={result.stderr.strip()!r}")
    if result.stdout:
        details.append(f"stdout={result.stdout.strip()!r}")
    raise _GitCheckIgnoreError(", ".join(details))


@pytest.mark.parametrize("path", _DURABLE_PATHS)
def test_durable_artifact_not_ignored(path: str) -> None:
    """Durable backlog artifact must not be matched by any .gitignore rule.

    Args:
        path: Repository-relative path under test.
    """
    assert not _git_ignores(path), (
        f"{path} is excluded by .gitignore but must be durable (Git-trackable)"
    )


@pytest.mark.parametrize("path", _VOLATILE_PATHS)
def test_volatile_artifact_is_ignored(path: str) -> None:
    """Volatile runtime artifact must remain excluded by .gitignore.

    Args:
        path: Repository-relative path under test.
    """
    assert _git_ignores(path), (
        f"{path} is not excluded by .gitignore but must remain volatile (not committed)"
    )


def test_git_ignores_raises_on_unexpected_git_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected git failures should raise an actionable exception."""

    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "check-ignore"],
            returncode=128,
            stdout="check-ignore failed",
            stderr="fatal: unable to read .gitignore",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(_GitCheckIgnoreError, match="git check-ignore failed") as exc_info:
        _git_ignores(".backlogit/queue/001-F.md")

    message = str(exc_info.value)
    assert "return code=128" in message
    assert "fatal: unable to read .gitignore" in message
    assert "check-ignore failed" in message


def test_git_ignores_raises_when_git_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing git executable should raise an actionable exception."""

    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(_GitCheckIgnoreError, match="git executable is not available") as exc_info:
        _git_ignores(".backlogit/queue/001-F.md")

    assert "PATH" in str(exc_info.value)
