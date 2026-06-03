"""CLI parity tests for the export-schema subcommand (010.005-T)."""

from __future__ import annotations

import io
import json
import sys

from docline.cli import main
from docline.schema.export import export_base_frontmatter_schema


def _capture_stdout(argv: list[str]) -> tuple[int, str]:
    """Run the CLI capturing stdout."""
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        exit_code = main(argv)
    finally:
        sys.stdout = saved
    return exit_code, buf.getvalue()


def test_cli_export_schema_prints_json_with_zero_exit() -> None:
    """``docline export-schema`` prints the JSON schema and exits 0."""
    exit_code, stdout = _capture_stdout(["export-schema"])
    assert exit_code == 0
    payload = json.loads(stdout)
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_cli_export_schema_matches_library_export() -> None:
    """CLI output must match the in-process library export byte-for-byte (parsed)."""
    _, stdout = _capture_stdout(["export-schema"])
    cli_schema = json.loads(stdout)
    lib_schema = export_base_frontmatter_schema()
    assert cli_schema == lib_schema


def test_mcp_export_schema_matches_cli_export() -> None:
    """MCP ``export_schema`` operation must return the same payload as the CLI."""
    from docline.mcp.server import DoclineMcpServer

    server = DoclineMcpServer()
    mcp_payload = server.export_schema()
    _, cli_stdout = _capture_stdout(["export-schema"])
    assert mcp_payload == cli_stdout.rstrip("\n")


def test_manifest_advertises_export_schema_tool() -> None:
    """The shared manifest must advertise the ``export_schema`` MCP tool."""
    from docline.app import get_manifest

    tools = {tool.name for tool in get_manifest().tools}
    assert "export_schema" in tools
