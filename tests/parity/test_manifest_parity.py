"""Tests for manifest parity between CLI, app, and MCP server surfaces."""

import json
import subprocess
import sys
from pathlib import Path

from docline.app import get_manifest
from docline.app_models import Manifest, McpManifestResponse
from docline.mcp.server import SERVER, get_manifest_response


def test_get_manifest_returns_manifest() -> None:
    """get_manifest() returns a Manifest instance."""
    manifest = get_manifest()
    assert isinstance(manifest, Manifest)


def test_manifest_has_three_tools() -> None:
    """Manifest contains the three documented tools: fetch, process, and export_schema."""
    manifest = get_manifest()
    assert len(manifest.tools) == 3


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
    assert "source" in fetch.parameters["properties"]


def test_manifest_process_parameters_has_staging_dir() -> None:
    """The process tool parameters include the 'staging_dir' field."""
    manifest = get_manifest()
    process = next(t for t in manifest.tools if t.name == "process")
    assert "staging_dir" in process.parameters["properties"]


def test_manifest_fetch_parameters_preserve_required_metadata() -> None:
    """The fetch tool parameters preserve full JSON Schema metadata."""
    manifest = get_manifest()
    fetch = next(t for t in manifest.tools if t.name == "fetch")
    assert fetch.parameters["type"] == "object"
    assert "required" in fetch.parameters
    assert "source" in fetch.parameters["required"]


def test_get_mcp_manifest_returns_mcp_manifest_response() -> None:
    """The MCP server surface returns a typed manifest envelope."""
    manifest = get_manifest_response()
    assert isinstance(manifest, McpManifestResponse)


def test_mcp_manifest_matches_shared_manifest() -> None:
    """The MCP server manifest surface exposes the shared tool schemas."""
    manifest = get_manifest()
    mcp_manifest = get_manifest_response()
    expected_tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters,
        }
        for tool in manifest.tools
    ]
    assert mcp_manifest.model_dump(by_alias=True)["tools"] == expected_tools


def test_mcp_server_list_tools_exposes_shared_manifest() -> None:
    """The MCP server surface exposes the shared tool set via list_tools()."""
    manifest = get_manifest()
    mcp_manifest = SERVER.list_tools()
    assert [tool["name"] for tool in mcp_manifest.model_dump(by_alias=True)["tools"]] == [
        tool.name for tool in manifest.tools
    ]


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


def test_cli_manifest_matches_mcp_manifest(capsys) -> None:
    """CLI and MCP server surfaces expose equivalent shared tool schemas."""
    from docline.cli import main

    main(["--manifest"])
    captured = capsys.readouterr()
    cli_manifest = json.loads(captured.out)
    mcp_manifest = get_manifest_response()
    assert [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["parameters"],
        }
        for tool in cli_manifest["tools"]
    ] == mcp_manifest.model_dump(by_alias=True)["tools"]


def test_cli_manifest_uses_parameters_field(capsys) -> None:
    """CLI manifest keeps the documented ``parameters`` field name."""
    from docline.cli import main

    main(["--manifest"])
    captured = capsys.readouterr()
    cli_manifest = json.loads(captured.out)
    assert "parameters" in cli_manifest["tools"][0]


def test_mcp_manifest_uses_input_schema_field() -> None:
    """MCP manifest uses the protocol-native ``inputSchema`` field name."""
    mcp_manifest = get_manifest_response().model_dump(by_alias=True)
    assert "inputSchema" in mcp_manifest["tools"][0]


def test_cli_fetch_missing_default_config_returns_1(capsys, monkeypatch, tmp_path) -> None:
    """CLI 'fetch' without a default config directory returns exit code 1."""
    from docline.cli import main

    monkeypatch.chdir(tmp_path)
    exit_code = main(["fetch"])
    assert exit_code == 1


def test_cli_process_no_staging_dir_returns_1(capsys) -> None:
    """CLI 'process' without an existing staging directory returns exit code 1."""
    from docline.cli import main

    exit_code = main(["process"])
    assert exit_code == 1


def test_cli_unknown_arg_returns_2(capsys) -> None:
    """CLI unknown args return exit code 2."""
    from docline.cli import main

    exit_code = main(["--unknown"])
    assert exit_code == 2


def test_python_m_docline_cli_runs_main() -> None:
    """Running ``python -m docline.cli`` executes the CLI entrypoint."""
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "docline.cli", "--manifest"],
        capture_output=True,
        check=False,
        cwd=repo_root,
        text=True,
    )

    assert result.returncode == 0
    assert "tools" in json.loads(result.stdout)
