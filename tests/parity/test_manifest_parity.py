"""Tests for manifest parity between CLI and app module."""

import json

from docline.app import get_manifest
from docline.app_models import Manifest


def test_get_manifest_returns_manifest() -> None:
    """get_manifest() returns a Manifest instance."""
    manifest = get_manifest()
    assert isinstance(manifest, Manifest)


def test_manifest_has_two_tools() -> None:
    """Manifest contains exactly two tools: fetch and process."""
    manifest = get_manifest()
    assert len(manifest.tools) == 2


def test_manifest_has_fetch_tool() -> None:
    """Manifest contains a 'fetch' tool."""
    manifest = get_manifest()
    names = [t.name for t in manifest.tools]
    assert "fetch" in names


def test_manifest_has_process_tool() -> None:
    """Manifest contains a 'process' tool."""
    manifest = get_manifest()
    names = [t.name for t in manifest.tools]
    assert "process" in names


def test_manifest_fetch_has_description() -> None:
    """The fetch tool has a non-empty description."""
    manifest = get_manifest()
    fetch = next(t for t in manifest.tools if t.name == "fetch")
    assert len(fetch.description) > 0


def test_manifest_process_has_description() -> None:
    """The process tool has a non-empty description."""
    manifest = get_manifest()
    process = next(t for t in manifest.tools if t.name == "process")
    assert len(process.description) > 0


def test_manifest_fetch_parameters_has_source() -> None:
    """The fetch tool parameters include the 'source' field."""
    manifest = get_manifest()
    fetch = next(t for t in manifest.tools if t.name == "fetch")
    assert "source" in fetch.parameters


def test_manifest_process_parameters_has_staging_dir() -> None:
    """The process tool parameters include the 'staging_dir' field."""
    manifest = get_manifest()
    process = next(t for t in manifest.tools if t.name == "process")
    assert "staging_dir" in process.parameters


def test_cli_manifest_flag_outputs_valid_json(capsys) -> None:
    """CLI --manifest flag prints valid JSON with 'tools' key."""
    from docline.cli import main

    exit_code = main(["--manifest"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "tools" in data


def test_cli_manifest_contains_fetch_and_process(capsys) -> None:
    """CLI --manifest JSON contains fetch and process tool entries."""
    from docline.cli import main

    main(["--manifest"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    names = [t["name"] for t in data["tools"]]
    assert "fetch" in names
    assert "process" in names


def test_cli_fetch_stub_returns_1(capsys) -> None:
    """CLI 'fetch' subcommand stub returns exit code 1."""
    from docline.cli import main

    exit_code = main(["fetch"])
    assert exit_code == 1


def test_cli_process_stub_returns_1(capsys) -> None:
    """CLI 'process' subcommand stub returns exit code 1."""
    from docline.cli import main

    exit_code = main(["process"])
    assert exit_code == 1


def test_cli_unknown_arg_returns_2(capsys) -> None:
    """CLI unknown args return exit code 2."""
    from docline.cli import main

    exit_code = main(["--unknown"])
    assert exit_code == 2
